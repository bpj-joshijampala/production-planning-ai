from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import MachineLoadSummary, PlannerOverride, PlannedOperation, Recommendation, ThroughputSummary
from app.services.planning_runs import recalculate_planning_run
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "planner_overrides_api.sqlite3"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", upload_dir.as_posix())
    monkeypatch.setenv("EXPORT_DIR", export_dir.as_posix())
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_create_planner_override_updates_recommendation_status_and_preserves_calculated_outputs(
    client: TestClient,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        recommendation = session.scalar(
            select(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
            .order_by(Recommendation.id.asc())
        )
        assert recommendation is not None
        snapshot_before = _calculated_output_snapshot(session, planning_run_id)

    response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation.id,
            "override_decision": "accept",
            "reason": "Planner accepts current recommendation.",
            "remarks": "Reviewed with production.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["planning_run_id"] == planning_run_id
    assert payload["recommendation_id"] == recommendation.id
    assert payload["entity_type"] == "RECOMMENDATION"
    assert payload["entity_id"] == recommendation.id
    assert payload["original_recommendation"] == recommendation.recommendation_type
    assert payload["override_decision"] == "ACCEPT"
    assert payload["reason"] == "Planner accepts current recommendation."
    assert payload["remarks"] == "Reviewed with production."
    assert payload["stale_flag"] is False
    assert payload["stale_reason"] is None
    assert payload["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert payload["user_display_name"] == "Development Planner"

    with session_factory() as session:
        snapshot_after = _calculated_output_snapshot(session, planning_run_id)
        updated_recommendation = session.get(Recommendation, recommendation.id)
        overrides = list(
            session.scalars(
                select(PlannerOverride)
                .where(PlannerOverride.planning_run_id == planning_run_id)
                .order_by(PlannerOverride.created_at.desc(), PlannerOverride.id.desc())
            )
        )

    assert snapshot_after == snapshot_before
    assert updated_recommendation is not None
    assert updated_recommendation.status == "ACCEPTED"
    assert len(overrides) == 1
    assert overrides[0].recommendation_id == recommendation.id
    assert overrides[0].override_decision == "ACCEPT"


def test_create_planner_override_for_non_recommendation_target_allows_missing_original_recommendation_and_does_not_mutate_recommendations(
    client: TestClient,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        recommendations_before = [
            (row.id, row.status)
            for row in session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.id.asc())
            )
        ]

    response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "VALVE",
            "entity_id": "V-100",
            "override_decision": "add_remarks",
            "reason": "Customer confirmation pending.",
            "remarks": None,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["entity_type"] == "VALVE"
    assert payload["entity_id"] == "V-100"
    assert payload["recommendation_id"] is None
    assert payload["original_recommendation"] is None
    assert payload["override_decision"] == "ADD_REMARKS"

    with session_factory() as session:
        recommendations_after = [
            (row.id, row.status)
            for row in session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.id.asc())
            )
        ]

    assert recommendations_after == recommendations_before


def test_create_planner_override_rejects_blank_reason(client: TestClient) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        recommendation = session.scalar(
            select(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
            .order_by(Recommendation.id.asc())
        )
        assert recommendation is not None

    response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation.id,
            "override_decision": "REJECT",
            "reason": "   ",
            "remarks": None,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "OVERRIDE_REQUIRES_REASON"

    with session_factory() as session:
        recommendation_after = session.get(Recommendation, recommendation.id)
        override_count = len(
            list(
                session.scalars(
                    select(PlannerOverride).where(PlannerOverride.planning_run_id == planning_run_id)
                )
            )
        )

    assert recommendation_after is not None
    assert recommendation_after.status == "PENDING"
    assert override_count == 0


def test_create_planner_override_rejects_unsupported_decision_without_mutating_recommendation(
    client: TestClient,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        recommendation = session.scalar(
            select(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
            .order_by(Recommendation.id.asc())
        )
        assert recommendation is not None
        recommendation_id = recommendation.id

    response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation_id,
            "override_decision": "teleport_to_vendor",
            "reason": "Unsupported decisions should not enter the audit log.",
            "remarks": None,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_OVERRIDE_DECISION"

    with session_factory() as session:
        recommendation_after = session.get(Recommendation, recommendation_id)
        override_count = len(
            list(
                session.scalars(
                    select(PlannerOverride).where(PlannerOverride.planning_run_id == planning_run_id)
                )
            )
        )

    assert recommendation_after is not None
    assert recommendation_after.status == "PENDING"
    assert override_count == 0


def test_list_planner_overrides_returns_append_only_log_in_descending_created_order(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)
    monkeypatch.setattr(
        "app.services.planner_overrides.utc_now_iso",
        iter(["2026-04-29T10:00:00Z", "2026-04-29T10:01:00Z"]).__next__,
    )

    session_factory = create_session_factory()
    with session_factory() as session:
        recommendation = session.scalar(
            select(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
            .order_by(Recommendation.id.asc())
        )
        assert recommendation is not None

    reject_response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation.id,
            "override_decision": "REJECT",
            "reason": "Planner rejects the recommendation.",
            "remarks": None,
        },
    )
    assert reject_response.status_code == 201

    with session_factory() as session:
        recommendation_after_reject = session.get(Recommendation, recommendation.id)
    assert recommendation_after_reject is not None
    assert recommendation_after_reject.status == "REJECTED"

    override_response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation.id,
            "override_decision": "FORCE_VENDOR",
            "reason": "Planner wants vendor route despite rejection.",
            "remarks": "Escalated for dispatch target.",
        },
    )
    assert override_response.status_code == 201

    with session_factory() as session:
        recommendation_after_override = session.get(Recommendation, recommendation.id)
    assert recommendation_after_override is not None
    assert recommendation_after_override.status == "OVERRIDDEN"

    response = client.get(f"/api/v1/planning-runs/{planning_run_id}/planner-overrides")

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_run_id"] == planning_run_id
    assert [
        (row["override_decision"], row["reason"], row["created_at"], row["user_display_name"])
        for row in payload["overrides"]
    ] == [
        (
            "FORCE_VENDOR",
            "Planner wants vendor route despite rejection.",
            "2026-04-29T10:01:00Z",
            "Development Planner",
        ),
        (
            "REJECT",
            "Planner rejects the recommendation.",
            "2026-04-29T10:00:00Z",
            "Development Planner",
        ),
    ]


def test_list_planner_overrides_surfaces_stale_flag_after_recalculation(
    client: TestClient,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        operation = session.scalar(
            select(PlannedOperation)
            .where(PlannedOperation.planning_run_id == planning_run_id)
            .order_by(PlannedOperation.sort_sequence.asc(), PlannedOperation.operation_no.asc(), PlannedOperation.id.asc())
        )
        assert operation is not None

    create_response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "OPERATION",
            "entity_id": operation.id,
            "override_decision": "FORCE_VENDOR",
            "reason": "Planner wants vendor route for this operation.",
            "remarks": None,
        },
    )
    assert create_response.status_code == 201

    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    list_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/planner-overrides")

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["stale_override_count"] == 1
    assert payload["current_override_count"] == 0
    assert payload["replanning_policy"] == (
        "Override-driven replanning is deferred in V1. Planner decisions remain audit records and are not "
        "replayed during recalculation."
    )
    assert [(row["entity_type"], row["override_decision"], row["stale_flag"]) for row in payload["overrides"]] == [
        ("OPERATION", "FORCE_VENDOR", True),
    ]
    assert payload["overrides"][0]["stale_reason"] == (
        "Operation target is stale or orphaned after recalculation. "
        "The decision remains in the action log but is not replayed in V1."
    )


def test_recalculation_marks_recommendation_decisions_stale_without_replaying_them(
    client: TestClient,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        recommendation = session.scalar(
            select(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
            .order_by(Recommendation.id.asc())
        )
        assert recommendation is not None
        recommendation_id = recommendation.id

    create_response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation_id,
            "override_decision": "ACCEPT",
            "reason": "Accept before recalculation.",
            "remarks": None,
        },
    )
    assert create_response.status_code == 201

    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    list_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/planner-overrides")

    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["stale_override_count"] == 1
    assert payload["current_override_count"] == 0
    assert [(row["entity_type"], row["entity_id"], row["stale_flag"]) for row in payload["overrides"]] == [
        ("RECOMMENDATION", recommendation_id, True),
    ]
    assert payload["overrides"][0]["stale_reason"] == (
        "Recommendation target is stale or orphaned after recalculation. "
        "The decision remains in the action log but is not replayed in V1."
    )

    with session_factory() as session:
        recalculated_recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.id.asc())
            )
        )
    assert recalculated_recommendations
    assert all(row.status == "PENDING" for row in recalculated_recommendations)


def _create_calculated_planning_run(client: TestClient) -> str:
    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", workbook_bytes(sheets=_planning_workbook_rows()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload_response.status_code == 201

    planning_run_response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_response.json()["id"],
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )
    assert planning_run_response.status_code == 201
    planning_run_id = str(planning_run_response.json()["id"])

    session_factory = create_session_factory()
    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    return planning_run_id


def _planning_workbook_rows() -> dict[str, list[list[object]]]:
    rows = minimal_workbook_rows()
    return rows


def _calculated_output_snapshot(session, planning_run_id: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "planned_operations": [
            (
                row.id,
                row.valve_id,
                row.component_line_no,
                row.component,
                row.operation_no,
                row.operation_name,
                row.machine_type,
                row.recommendation_status,
                row.internal_wait_days,
                row.processing_time_days,
                row.internal_completion_offset_days,
            )
            for row in session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc(), PlannedOperation.operation_no.asc(), PlannedOperation.id.asc())
            )
        ],
        "machine_load": [
            (
                row.machine_type,
                row.total_operation_hours,
                row.load_days,
                row.buffer_days,
                row.overload_flag,
                row.batch_risk_flag,
                row.status,
            )
            for row in session.scalars(
                select(MachineLoadSummary)
                .where(MachineLoadSummary.planning_run_id == planning_run_id)
                .order_by(MachineLoadSummary.machine_type.asc())
            )
        ],
        "throughput": [
            (
                row.target_throughput_value_cr,
                row.planned_throughput_value_cr,
                row.throughput_gap_cr,
                row.throughput_risk_flag,
            )
            for row in session.scalars(
                select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
            )
        ],
        "recommendations": [
            (
                row.id,
                row.recommendation_type,
                row.valve_id,
                row.component_line_no,
                row.component,
                row.operation_name,
                row.machine_type,
                row.suggested_machine_type,
                row.suggested_vendor_id,
                row.suggested_vendor_name,
                row.internal_wait_days,
                row.processing_time_days,
                row.internal_completion_days,
                row.vendor_total_days,
                row.vendor_gain_days,
                row.subcontract_batch_candidate_count,
                row.batch_subcontract_opportunity_flag,
                row.reason_codes_json,
                row.explanation,
            )
            for row in session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.id.asc())
            )
        ],
    }
