from collections.abc import Generator
from copy import deepcopy

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import (
    FlowBlocker,
    IncomingLoadItem,
    MachineLoadSummary,
    PlannerOverride,
    PlannedOperation,
    Recommendation,
    ThroughputSummary,
    ValveReadinessSummary,
    VendorLoadSummary,
)
from app.models.planning_run import PlanningRun, PlanningSnapshot
from app.planning.input_loader import PlanningSettingsOverride
from app.models.upload import UploadBatch
from app.services.planning_runs import recalculate_planning_run
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "planning_run_calculation.sqlite3"
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


def test_recalculate_planning_run_populates_core_outputs_and_marks_run_calculated(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_run = recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    assert planning_run.status == "CALCULATED"
    assert planning_run.calculated_at is not None
    assert planning_run.error_message is None

    with session_factory() as session:
        upload = session.scalar(select(UploadBatch).where(UploadBatch.id == planning_run.upload_batch_id))
        incoming_count = session.scalar(
            select(func.count()).select_from(IncomingLoadItem).where(IncomingLoadItem.planning_run_id == planning_run_id)
        )
        planned_count = session.scalar(
            select(func.count()).select_from(PlannedOperation).where(PlannedOperation.planning_run_id == planning_run_id)
        )
        blocker_count = session.scalar(
            select(func.count()).select_from(FlowBlocker).where(FlowBlocker.planning_run_id == planning_run_id)
        )
        machine_count = session.scalar(
            select(func.count()).select_from(MachineLoadSummary).where(MachineLoadSummary.planning_run_id == planning_run_id)
        )
        readiness_count = session.scalar(
            select(func.count()).select_from(ValveReadinessSummary).where(
                ValveReadinessSummary.planning_run_id == planning_run_id
            )
        )
        recommendation_count = session.scalar(
            select(func.count()).select_from(Recommendation).where(Recommendation.planning_run_id == planning_run_id)
        )
        throughput = session.scalar(
            select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
        )
        vendor_load_count = session.scalar(
            select(func.count()).select_from(VendorLoadSummary).where(VendorLoadSummary.planning_run_id == planning_run_id)
        )

    assert upload is not None
    assert upload.status == "CALCULATED"
    assert incoming_count == 2
    assert planned_count == 3
    assert blocker_count == 1
    assert machine_count == 2
    assert readiness_count == 2
    assert recommendation_count == 3
    assert throughput is not None
    assert throughput.target_throughput_value_cr == pytest.approx(2.5)
    assert throughput.planned_throughput_value_cr == pytest.approx(1.75)
    assert throughput.throughput_gap_cr == pytest.approx(0.75)
    assert throughput.throughput_risk_flag == 1
    assert vendor_load_count == 1


def test_recalculate_planning_run_replaces_prior_calculated_outputs(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        throughput = session.scalar(
            select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
        )
        assert throughput is not None
        throughput.target_throughput_value_cr = 999.0
        throughput.planned_throughput_value_cr = 999.0
        throughput.throughput_gap_cr = 0.0
        throughput.throughput_risk_flag = 0
        session.add(
            FlowBlocker(
                id="extra-blocker",
                planning_run_id=planning_run_id,
                planned_operation_id=None,
                valve_id=None,
                component_line_no=None,
                component=None,
                operation_name=None,
                blocker_type="MACHINE_OVERLOAD",
                cause="Bogus blocker",
                recommended_action="Ignore",
                severity="WARNING",
            )
        )
        session.commit()

    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc())
            )
        )
        throughput = session.scalar(
            select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
        )

    assert [row.blocker_type for row in blockers] == ["BATCH_RISK"]
    assert throughput is not None
    assert throughput.target_throughput_value_cr == pytest.approx(2.5)
    assert throughput.planned_throughput_value_cr == pytest.approx(1.75)
    assert throughput.throughput_gap_cr == pytest.approx(0.75)
    assert throughput.throughput_risk_flag == 1


def test_recalculate_planning_run_is_deterministic_across_consecutive_runs(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        first_snapshot = _output_snapshot(session=session, planning_run_id=planning_run_id)

    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        second_snapshot = _output_snapshot(session=session, planning_run_id=planning_run_id)

    assert second_snapshot == first_snapshot


def test_recalculate_planning_run_persists_subcontract_and_vendor_unavailable_paths(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows_with_subcontract_paths()))

    session_factory = create_session_factory()
    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.valve_id.asc(), Recommendation.operation_name.asc())
            )
        )
        flow_blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc(), FlowBlocker.operation_name.asc())
            )
        )

    assert [
        (row.valve_id, row.component, row.operation_name, row.recommendation_type, row.suggested_vendor_id)
        for row in recommendations
    ] == [
        ("V-100", "Body", "HBM roughing", "SUBCONTRACT", "VEN-1"),
        ("V-100", "Body", "VTL finish", "OK_INTERNAL", None),
        ("V-200", "Bonnet", "HBM finish", "NO_FEASIBLE_OPTION", None),
    ]
    assert ("VENDOR_UNAVAILABLE", "V-200", "Bonnet", "HBM finish", "WARNING") in [
        (row.blocker_type, row.valve_id, row.component, row.operation_name, row.severity)
        for row in flow_blockers
    ]


def test_recalculate_planning_run_persists_batch_subcontract_opportunity_and_vendor_load(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows_with_batch_subcontract()))

    session_factory = create_session_factory()
    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.valve_id.asc(), Recommendation.operation_name.asc())
            )
        )
        planned_operations = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.valve_id.asc(), PlannedOperation.operation_no.asc())
            )
        )
        vendor_load = list(
            session.scalars(
                select(VendorLoadSummary)
                .where(VendorLoadSummary.planning_run_id == planning_run_id)
                .order_by(VendorLoadSummary.vendor_id.asc())
            )
        )

    assert [
        (
            row.valve_id,
            row.component,
            row.operation_name,
            row.recommendation_type,
            row.suggested_vendor_id,
            row.subcontract_batch_candidate_count,
            row.batch_subcontract_opportunity_flag,
        )
        for row in recommendations
    ] == [
        ("V-100", "Body", "HBM roughing", "BATCH_SUBCONTRACT_OPPORTUNITY", "VEN-1", 2, 1),
        ("V-100", "Body", "VTL finish", "OK_INTERNAL", None, None, 0),
        ("V-200", "Bonnet", "HBM finish", "BATCH_SUBCONTRACT_OPPORTUNITY", "VEN-1", 2, 1),
    ]
    assert [
        (row.valve_id, row.component, row.operation_name, row.recommendation_status)
        for row in planned_operations
    ] == [
        ("V-100", "Body", "HBM roughing", "SUBCONTRACT"),
        ("V-100", "Body", "VTL finish", "OK_INTERNAL"),
        ("V-200", "Bonnet", "HBM finish", "SUBCONTRACT"),
    ]
    assert [(row.vendor_id, row.vendor_recommended_jobs, row.status) for row in vendor_load] == [
        ("VEN-1", 2, "OK"),
    ]


def test_recalculate_planning_run_persists_hold_for_priority_flow_and_missing_component_blockers(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows_with_priority_hold()))

    session_factory = create_session_factory()
    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.valve_id.asc(), Recommendation.operation_name.asc())
            )
        )
        blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc(), FlowBlocker.component_line_no.asc())
            )
        )

    assert [
        (row.valve_id, row.component, row.operation_name, row.recommendation_type)
        for row in recommendations
    ] == [
        ("V-100", "Body", "HBM roughing", "OK_INTERNAL"),
        ("V-300", "Seat", "HBM finish", "HOLD_FOR_PRIORITY_FLOW"),
    ]
    assert [
        (row.blocker_type, row.valve_id, row.component, row.severity)
        for row in blockers
        if row.blocker_type == "MISSING_COMPONENT"
    ] == [
        ("MISSING_COMPONENT", "V-300", "Bonnet", "WARNING"),
        ("MISSING_COMPONENT", "V-300", "Stem", "WARNING"),
        ("MISSING_COMPONENT", "V-300", "Gate", "WARNING"),
    ]


def test_recalculate_planning_run_preserves_overrides_and_marks_missing_operation_targets_stale(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)
        operation = session.scalar(
            select(PlannedOperation)
            .where(PlannedOperation.planning_run_id == planning_run_id)
            .order_by(PlannedOperation.sort_sequence.asc())
        )
        assert operation is not None
        session.add_all(
            [
                PlannerOverride(
                    id="override-operation",
                    planning_run_id=planning_run_id,
                    recommendation_id=None,
                    entity_type="OPERATION",
                    entity_id=operation.id,
                    original_recommendation="OK_INTERNAL",
                    override_decision="FORCE_VENDOR",
                    reason="Expedite externally",
                    remarks=None,
                    stale_flag=0,
                    user_id="00000000-0000-0000-0000-000000000001",
                    created_at="2026-04-25T00:00:00Z",
                ),
                PlannerOverride(
                    id="override-valve",
                    planning_run_id=planning_run_id,
                    recommendation_id=None,
                    entity_type="VALVE",
                    entity_id="V-100",
                    original_recommendation=None,
                    override_decision="HOLD",
                    reason="Customer confirmation pending",
                    remarks=None,
                    stale_flag=0,
                    user_id="00000000-0000-0000-0000-000000000001",
                    created_at="2026-04-25T00:01:00Z",
                ),
            ]
        )
        session.commit()

    with session_factory() as session:
        recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        overrides = list(
            session.scalars(
                select(PlannerOverride)
                .where(PlannerOverride.planning_run_id == planning_run_id)
                .order_by(PlannerOverride.id.asc())
            )
        )

    assert [(row.id, row.entity_type, row.stale_flag) for row in overrides] == [
        ("override-operation", "OPERATION", 1),
        ("override-valve", "VALVE", 0),
    ]


def test_recalculate_planning_run_preserves_prior_outputs_when_rerun_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        first_run = recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    original_calculated_at = first_run.calculated_at

    def fail_throughput(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic throughput failure")

    monkeypatch.setattr("app.services.planning_runs.calculate_and_persist_throughput_summary", fail_throughput)

    with session_factory() as session:
        with pytest.raises(RuntimeError, match="synthetic throughput failure"):
            recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        planning_run = session.get(PlanningRun, planning_run_id)
        throughput = session.scalar(
            select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
        )
        blocker_count = session.scalar(
            select(func.count()).select_from(FlowBlocker).where(FlowBlocker.planning_run_id == planning_run_id)
        )
        incoming_count = session.scalar(
            select(func.count()).select_from(IncomingLoadItem).where(IncomingLoadItem.planning_run_id == planning_run_id)
        )

    assert planning_run is not None
    assert planning_run.status == "FAILED"
    assert planning_run.error_message is not None
    assert "synthetic throughput failure" in planning_run.error_message
    assert planning_run.calculated_at == original_calculated_at
    assert throughput is not None
    assert throughput.target_throughput_value_cr == pytest.approx(2.5)
    assert throughput.planned_throughput_value_cr == pytest.approx(1.75)
    assert throughput.throughput_gap_cr == pytest.approx(0.75)
    assert throughput.throughput_risk_flag == 1
    assert blocker_count == 1
    assert incoming_count == 2


def test_calculate_planning_run_endpoint_returns_structured_failure_and_rolls_back_partial_outputs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))
    logged_messages: list[str] = []

    def fail_throughput(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic throughput failure")

    def capture_exception(message: str, *args: object, **_kwargs: object) -> None:
        logged_messages.append(message % args)

    monkeypatch.setattr("app.services.planning_runs.calculate_and_persist_throughput_summary", fail_throughput)
    monkeypatch.setattr("app.services.planning_runs.logger.exception", capture_exception)
    monkeypatch.setattr("app.api.v1.planning_runs.logger.exception", capture_exception)

    response = client.post(f"/api/v1/planning-runs/{planning_run_id}/calculate")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "CALCULATION_FAILED",
        "message": "Planning calculation failed. Review the PlanningRun error message, fix the input data or settings, and retry.",
    }
    assert logged_messages == [
        f"PlanningRun recalculation failed planning_run_id={planning_run_id}",
        f"Planning calculation failed planning_run_id={planning_run_id}",
    ]

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_run = session.get(PlanningRun, planning_run_id)
        output_counts = {
            model.__name__: session.scalar(
                select(func.count()).select_from(model).where(model.planning_run_id == planning_run_id)
            )
            for model in (
                IncomingLoadItem,
                PlannedOperation,
                MachineLoadSummary,
                ValveReadinessSummary,
                FlowBlocker,
                Recommendation,
                ThroughputSummary,
                VendorLoadSummary,
            )
        }

    assert planning_run is not None
    assert planning_run.status == "FAILED"
    assert planning_run.calculated_at is None
    assert planning_run.error_message is not None
    assert "synthetic throughput failure" in planning_run.error_message
    assert output_counts == {
        "IncomingLoadItem": 0,
        "PlannedOperation": 0,
        "MachineLoadSummary": 0,
        "ValveReadinessSummary": 0,
        "FlowBlocker": 0,
        "Recommendation": 0,
        "ThroughputSummary": 0,
        "VendorLoadSummary": 0,
    }


def test_recalculate_planning_run_with_settings_override_persists_run_settings_and_snapshot(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_run = recalculate_planning_run(
            planning_run_id=planning_run_id,
            db=session,
            settings_override=PlanningSettingsOverride(planning_horizon_days=14),
        )

    assert planning_run.planning_horizon_days == 14

    with session_factory() as session:
        persisted_run = session.get(PlanningRun, planning_run_id)
        snapshot = session.scalar(select(PlanningSnapshot).where(PlanningSnapshot.planning_run_id == planning_run_id))
        throughput = session.scalar(
            select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
        )

    assert persisted_run is not None
    assert persisted_run.planning_horizon_days == 14
    assert snapshot is not None
    assert '"planning_horizon_days":14' in snapshot.snapshot_json
    assert throughput is not None
    assert throughput.target_throughput_value_cr == pytest.approx(5.0)


def test_recalculate_planning_run_marks_run_failed_when_initial_flush_raises(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_planning_workbook_rows()))

    original_flush = Session.flush
    state = {"failed_once": False}

    def fail_once_flush(session: Session, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not state["failed_once"]:
            state["failed_once"] = True
            raise RuntimeError("synthetic flush failure")
        return original_flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", fail_once_flush)

    session_factory = create_session_factory()
    with session_factory() as session:
        with pytest.raises(RuntimeError, match="synthetic flush failure"):
            recalculate_planning_run(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        planning_run = session.get(PlanningRun, planning_run_id)

    assert planning_run is not None
    assert planning_run.status == "FAILED"
    assert planning_run.error_message is not None
    assert "synthetic flush failure" in planning_run.error_message


def _create_planning_run(client: TestClient, workbook_content: bytes) -> str:
    upload_response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                "plan.xlsx",
                workbook_content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
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
    return str(planning_run_response.json()["id"])


def _planning_workbook_rows() -> dict[str, list[list[object]]]:
    rows = deepcopy(minimal_workbook_rows())

    rows["Valve_Plan"][0] = [
        "Valve_ID",
        "Order_ID",
        "Customer",
        "Dispatch_Date",
        "Assembly_Date",
        "Value_Cr",
        "Priority",
    ]
    rows["Valve_Plan"][1] = ["V-100", "O-100", "Acme", "2026-05-01", "2026-04-22", 1.25, "A"]
    rows["Valve_Plan"].append(["V-200", "O-200", "Beta", "2026-05-02", "2026-04-24", 0.5, "B"])

    rows["Component_Status"][0] = [
        "Valve_ID",
        "Component_Line_No",
        "Component",
        "Qty",
        "Fabrication_Required",
        "Fabrication_Complete",
        "Expected_Ready_Date",
        "Critical",
        "Ready_Date_Type",
    ]
    rows["Component_Status"][1] = ["V-100", 1, "Body", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED"]
    rows["Component_Status"].append(["V-200", 1, "Bonnet", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "N"]
    rows["Routing_Master"].append(["Body", 20, "VTL finish", "VTL", 4, "N"])
    rows["Routing_Master"].append(["Bonnet", 10, "HBM finish", "HBM", 8, "N"])

    rows["Machine_Master"][0] = [
        "Machine_ID",
        "Machine_Type",
        "Hours_per_Day",
        "Efficiency_Percent",
        "Buffer_Days",
        "Active",
    ]
    rows["Machine_Master"][1] = ["HBM-1", "HBM", 8, 100, 5, "Y"]
    rows["Machine_Master"].append(["VTL-1", "VTL", 8, 100, 3, "Y"])

    return rows


def _planning_workbook_rows_with_subcontract_paths() -> dict[str, list[list[object]]]:
    rows = deepcopy(minimal_workbook_rows())

    rows["Valve_Plan"][0] = [
        "Valve_ID",
        "Order_ID",
        "Customer",
        "Dispatch_Date",
        "Assembly_Date",
        "Value_Cr",
        "Priority",
    ]
    rows["Valve_Plan"][1] = ["V-100", "O-100", "Acme", "2026-05-01", "2026-04-22", 1.25, "A"]
    rows["Valve_Plan"].append(["V-200", "O-200", "Beta", "2026-05-02", "2026-04-24", 0.5, "B"])

    rows["Component_Status"][0] = [
        "Valve_ID",
        "Component_Line_No",
        "Component",
        "Qty",
        "Fabrication_Required",
        "Fabrication_Complete",
        "Expected_Ready_Date",
        "Critical",
        "Ready_Date_Type",
    ]
    rows["Component_Status"][1] = ["V-100", 1, "Body", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED"]
    rows["Component_Status"].append(["V-200", 1, "Bonnet", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
        "Vendor_Process",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "Y", ""]
    rows["Routing_Master"].append(["Body", 20, "VTL finish", "VTL", 4, "N", ""])
    rows["Routing_Master"].append(["Bonnet", 10, "HBM finish", "HBM", 8, "Y", "EDM"])

    rows["Machine_Master"][0] = [
        "Machine_ID",
        "Machine_Type",
        "Hours_per_Day",
        "Efficiency_Percent",
        "Buffer_Days",
        "Active",
    ]
    rows["Machine_Master"][1] = ["HBM-1", "HBM", 8, 100, 1, "Y"]
    rows["Machine_Master"].append(["VTL-1", "VTL", 8, 100, 3, "Y"])

    rows["Vendor_Master"][0] = [
        "Vendor_ID",
        "Vendor_Name",
        "Primary_Process",
        "Turnaround_Days",
        "Transport_Days_Total",
        "Capacity_Rating",
        "Reliability",
        "Approved",
    ]
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 0, 0, "Medium", "A", "Y"]

    return rows


def _planning_workbook_rows_with_batch_subcontract() -> dict[str, list[list[object]]]:
    rows = _planning_workbook_rows_with_subcontract_paths()
    rows["Routing_Master"][3] = ["Bonnet", 10, "HBM finish", "HBM", 8, "Y", "HBM"]
    return rows


def _planning_workbook_rows_with_priority_hold() -> dict[str, list[list[object]]]:
    rows = deepcopy(minimal_workbook_rows())

    rows["Valve_Plan"][0] = [
        "Valve_ID",
        "Order_ID",
        "Customer",
        "Dispatch_Date",
        "Assembly_Date",
        "Value_Cr",
        "Priority",
    ]
    rows["Valve_Plan"][1] = ["V-100", "O-100", "Acme", "2026-05-01", "2026-04-22", 1.25, "A"]
    rows["Valve_Plan"].append(["V-300", "O-300", "Gamma", "2026-05-03", "2026-04-28", 0.4, "C"])

    rows["Component_Status"][0] = [
        "Valve_ID",
        "Component_Line_No",
        "Component",
        "Qty",
        "Fabrication_Required",
        "Fabrication_Complete",
        "Expected_Ready_Date",
        "Critical",
        "Ready_Date_Type",
    ]
    rows["Component_Status"][1] = ["V-100", 1, "Body", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED"]
    rows["Component_Status"].append(["V-300", 1, "Seat", 1, "N", "Y", "2026-04-22", "Y", "CONFIRMED"])
    rows["Component_Status"].append(["V-300", 2, "Bonnet", 1, "Y", "N", "2026-05-02", "Y", "EXPECTED"])
    rows["Component_Status"].append(["V-300", 3, "Stem", 1, "Y", "N", "2026-05-03", "Y", "EXPECTED"])
    rows["Component_Status"].append(["V-300", 4, "Gate", 1, "Y", "N", "2026-05-04", "Y", "EXPECTED"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
        "Vendor_Process",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "N", ""]
    rows["Routing_Master"].append(["Seat", 10, "HBM finish", "HBM", 8, "N", ""])
    rows["Routing_Master"].append(["Bonnet", 10, "HBM prep", "HBM", 4, "N", ""])
    rows["Routing_Master"].append(["Stem", 10, "HBM turn", "HBM", 4, "N", ""])
    rows["Routing_Master"].append(["Gate", 10, "HBM mill", "HBM", 4, "N", ""])

    rows["Machine_Master"][0] = [
        "Machine_ID",
        "Machine_Type",
        "Hours_per_Day",
        "Efficiency_Percent",
        "Buffer_Days",
        "Active",
    ]
    rows["Machine_Master"][1] = ["HBM-1", "HBM", 8, 100, 2.5, "Y"]

    rows["Vendor_Master"][0] = [
        "Vendor_ID",
        "Vendor_Name",
        "Primary_Process",
        "Turnaround_Days",
        "Transport_Days_Total",
        "Capacity_Rating",
        "Reliability",
        "Approved",
    ]
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 1, 0, "Medium", "A", "Y"]

    return rows


def _output_snapshot(*, session: Session, planning_run_id: str) -> dict[str, object]:
    return {
        "incoming_load": [
            (
                row.valve_id,
                row.component_line_no,
                row.component,
                row.availability_date,
                row.priority_score,
                row.sort_sequence,
                row.batch_risk_flag,
            )
            for row in session.scalars(
                select(IncomingLoadItem)
                .where(IncomingLoadItem.planning_run_id == planning_run_id)
                .order_by(IncomingLoadItem.sort_sequence.asc())
            )
        ],
        "planned_operations": [
            (
                row.valve_id,
                row.component_line_no,
                row.component,
                row.operation_no,
                row.machine_type,
                row.sort_sequence,
                row.operation_arrival_offset_days,
                row.scheduled_start_offset_days,
                row.internal_wait_days,
                row.processing_time_days,
                row.internal_completion_offset_days,
                row.extreme_delay_flag,
            )
            for row in session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc(), PlannedOperation.operation_no.asc())
            )
        ],
        "flow_blockers": [
            (
                row.blocker_type,
                row.valve_id,
                row.component_line_no,
                row.component,
                row.operation_name,
                row.cause,
                row.recommended_action,
                row.severity,
            )
            for row in session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc(), FlowBlocker.component.asc())
            )
        ],
        "machine_summaries": [
            (
                row.machine_type,
                row.total_operation_hours,
                row.capacity_hours_per_day,
                row.load_days,
                row.buffer_days,
                row.overload_flag,
                row.overload_days,
                row.spare_capacity_days,
                row.underutilized_flag,
                row.batch_risk_flag,
                row.status,
                row.queue_approximation_warning,
            )
            for row in session.scalars(
                select(MachineLoadSummary)
                .where(MachineLoadSummary.planning_run_id == planning_run_id)
                .order_by(MachineLoadSummary.machine_type.asc())
            )
        ],
        "readiness": [
            (
                row.valve_id,
                row.ready_components,
                row.required_components,
                row.pending_required_count,
                row.full_kit_flag,
                row.near_ready_flag,
                row.valve_expected_completion_date,
                row.otd_delay_days,
                row.otd_risk_flag,
                row.readiness_status,
                row.risk_reason,
            )
            for row in session.scalars(
                select(ValveReadinessSummary)
                .where(ValveReadinessSummary.planning_run_id == planning_run_id)
                .order_by(ValveReadinessSummary.valve_id.asc())
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
                select(ThroughputSummary)
                .where(ThroughputSummary.planning_run_id == planning_run_id)
            )
        ],
        "recommendations": [
            (
                row.valve_id,
                row.component_line_no,
                row.component,
                row.operation_name,
                row.recommendation_type,
                row.machine_type,
                row.suggested_vendor_id,
                row.status,
                row.reason_codes_json,
            )
            for row in session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(
                    Recommendation.valve_id.asc(),
                    Recommendation.component_line_no.asc(),
                    Recommendation.component.asc(),
                    Recommendation.operation_name.asc(),
                    Recommendation.machine_type.asc(),
                    Recommendation.id.asc(),
                )
            )
        ],
        "vendor_load": [
            (
                row.vendor_id,
                row.primary_process,
                row.vendor_recommended_jobs,
                row.max_recommended_jobs_per_horizon,
                row.selected_vendor_overloaded_flag,
                row.status,
            )
            for row in session.scalars(
                select(VendorLoadSummary)
                .where(VendorLoadSummary.planning_run_id == planning_run_id)
                .order_by(VendorLoadSummary.vendor_id.asc(), VendorLoadSummary.primary_process.asc())
            )
        ],
    }
