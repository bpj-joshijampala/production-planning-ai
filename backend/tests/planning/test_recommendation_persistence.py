from collections.abc import Generator
from copy import deepcopy
import json

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import FlowBlocker, PlannedOperation, Recommendation, VendorLoadSummary
from app.services.machine_load import calculate_and_persist_machine_load
from app.services.recommendations import calculate_and_persist_placeholder_recommendations
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "recommendations.sqlite3"
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


def test_calculate_and_persist_placeholder_recommendations_populates_recommendation_status_and_vendor_load(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_recommendation_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        result = calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    assert {
        (row.component, row.operation_name): row.recommendation_type
        for row in result.recommendations
    } == {
        ("Body", "HBM roughing"): "NO_FEASIBLE_OPTION",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.operation_name.asc(), Recommendation.id.asc())
            )
        )
        planned_operations = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc())
            )
        )
        vendor_load = list(
            session.scalars(
                select(VendorLoadSummary)
                .where(VendorLoadSummary.planning_run_id == planning_run_id)
                .order_by(VendorLoadSummary.vendor_id.asc())
            )
        )
        flow_blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc(), FlowBlocker.operation_name.asc())
            )
        )

    assert {
        (row.component, row.operation_name): row.recommendation_type
        for row in recommendations
    } == {
        ("Body", "HBM roughing"): "NO_FEASIBLE_OPTION",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }
    assert {
        (row.component, row.operation_name): row.recommendation_status
        for row in planned_operations
    } == {
        ("Body", "HBM roughing"): "NO_FEASIBLE_OPTION",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }
    assert [(row.vendor_id, row.vendor_recommended_jobs, row.status) for row in vendor_load] == [
        ("VEN-1", 1, "OK"),
        ("VEN-2", 0, "OK"),
    ]
    assert not any(row.blocker_type == "VENDOR_UNAVAILABLE" for row in flow_blockers)

    subcontract = next(row for row in recommendations if row.operation_name == "HBM finish")
    assert subcontract.suggested_vendor_id == "VEN-1"
    assert subcontract.vendor_total_days == pytest.approx(1.0)
    assert subcontract.vendor_gain_days == pytest.approx(1.0)
    assert "External pending load and vendor timing are only partially modeled in V1." in subcontract.explanation


def test_calculate_and_persist_placeholder_recommendations_persists_vendor_unavailable_only_for_no_approved_vendor(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_no_approved_vendor_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        result = calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    assert {
        (row.component, row.operation_name): row.recommendation_type
        for row in result.recommendations
    } == {
        ("Body", "HBM roughing"): "NO_FEASIBLE_OPTION",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }

    with session_factory() as session:
        flow_blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc(), FlowBlocker.operation_name.asc())
            )
        )

    vendor_unavailable = next(row for row in flow_blockers if row.blocker_type == "VENDOR_UNAVAILABLE")
    assert vendor_unavailable.operation_name == "HBM roughing"
    assert vendor_unavailable.severity == "CRITICAL"
    assert "No approved vendor exists for process EDM." in vendor_unavailable.cause
    assert vendor_unavailable.recommended_action == "Add an approved vendor for this process or keep the operation in-house with escalation."


def test_calculate_and_persist_placeholder_recommendations_persists_use_alternate_before_machine_overload(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_alternate_machine_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        result = calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    assert {
        (row.component, row.operation_name): row.recommendation_type
        for row in result.recommendations
    } == {
        ("Body", "HBM roughing"): "USE_ALTERNATE",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.operation_name.asc(), Recommendation.id.asc())
            )
        )
        planned_operations = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc())
            )
        )

    alternate = next(row for row in recommendations if row.operation_name == "HBM roughing")
    assert alternate.recommendation_type == "USE_ALTERNATE"
    assert alternate.suggested_machine_type == "VTL"
    assert "HBM load_days 2.00 exceeds buffer_days 1.00" in alternate.explanation
    assert "VTL load_days after assignment 1.50 stays within buffer_days 3.00" in alternate.explanation

    subcontract = next(row for row in recommendations if row.operation_name == "HBM finish")
    assert subcontract.recommendation_type == "SUBCONTRACT"
    assert subcontract.suggested_vendor_id == "VEN-1"
    assert subcontract.vendor_total_days == pytest.approx(1.0)

    assert {
        (row.component, row.operation_name): row.recommendation_status
        for row in planned_operations
    } == {
        ("Body", "HBM roughing"): "USE_ALTERNATE",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }


def test_calculate_and_persist_placeholder_recommendations_holds_non_full_kit_work_for_priority_flow(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_hold_for_priority_flow_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        result = calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    assert {
        (row.valve_id, row.component, row.operation_name): row.recommendation_type
        for row in result.recommendations
    } == {
        ("V-100", "Body", "HBM roughing"): "OK_INTERNAL",
        ("V-300", "Seat", "HBM finish"): "HOLD_FOR_PRIORITY_FLOW",
    }

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

    hold = next(row for row in recommendations if row.valve_id == "V-300")
    assert hold.recommendation_type == "HOLD_FOR_PRIORITY_FLOW"
    assert json.loads(hold.reason_codes_json) == ["HOLD_FOR_PRIORITY_FLOW"]
    assert "priority_load_days" in hold.explanation
    assert "Hold this operation for priority flow." in hold.explanation
    assert {
        (row.valve_id, row.component, row.operation_name): row.recommendation_status
        for row in planned_operations
    } == {
        ("V-100", "Body", "HBM roughing"): "OK_INTERNAL",
        ("V-300", "Seat", "HBM finish"): "HOLD_FOR_PRIORITY_FLOW",
    }


def test_calculate_and_persist_placeholder_recommendations_limits_shared_alternate_capacity(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_alternate_machine_contention_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        result = calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    assert {
        (row.component, row.operation_name): row.recommendation_type
        for row in result.recommendations
    } == {
        ("Body", "HBM roughing"): "USE_ALTERNATE",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.operation_name.asc(), Recommendation.id.asc())
            )
        )

    assert [
        (row.component, row.operation_name, row.recommendation_type, row.suggested_machine_type)
        for row in recommendations
    ] == [
        ("Bonnet", "HBM finish", "SUBCONTRACT", None),
        ("Body", "HBM roughing", "USE_ALTERNATE", "VTL"),
        ("Body", "VTL finish", "OK_INTERNAL", None),
    ]


def test_calculate_and_persist_placeholder_recommendations_flags_batch_subcontract_opportunity(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_batch_subcontract_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        result = calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    assert {
        (row.component, row.operation_name): (
            row.recommendation_type,
            row.recommendation_status,
            row.subcontract_batch_candidate_count,
            row.batch_subcontract_opportunity_flag,
        )
        for row in result.recommendations
    } == {
        ("Body", "HBM roughing"): ("BATCH_SUBCONTRACT_OPPORTUNITY", "SUBCONTRACT", 2, True),
        ("Body", "VTL finish"): ("OK_INTERNAL", "OK_INTERNAL", None, False),
        ("Bonnet", "HBM finish"): ("BATCH_SUBCONTRACT_OPPORTUNITY", "SUBCONTRACT", 2, True),
    }

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.operation_name.asc(), Recommendation.id.asc())
            )
        )
        planned_operations = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc())
            )
        )
        vendor_load = list(
            session.scalars(
                select(VendorLoadSummary)
                .where(VendorLoadSummary.planning_run_id == planning_run_id)
                .order_by(VendorLoadSummary.vendor_id.asc())
            )
        )

    assert {
        (row.component, row.operation_name): (
            row.recommendation_type,
            row.subcontract_batch_candidate_count,
            row.batch_subcontract_opportunity_flag,
        )
        for row in recommendations
    } == {
        ("Body", "HBM roughing"): ("BATCH_SUBCONTRACT_OPPORTUNITY", 2, 1),
        ("Body", "VTL finish"): ("OK_INTERNAL", None, 0),
        ("Bonnet", "HBM finish"): ("BATCH_SUBCONTRACT_OPPORTUNITY", 2, 1),
    }
    assert {
        (row.component, row.operation_name): row.recommendation_status
        for row in planned_operations
    } == {
        ("Body", "HBM roughing"): "SUBCONTRACT",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "SUBCONTRACT",
    }
    assert [(row.vendor_id, row.vendor_recommended_jobs, row.status) for row in vendor_load] == [
        ("VEN-1", 2, "OK"),
        ("VEN-2", 0, "OK"),
    ]


def test_calculate_and_persist_placeholder_recommendations_creates_vendor_overloaded_blocker(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_vendor_overload_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        vendor_load = list(
            session.scalars(
                select(VendorLoadSummary)
                .where(VendorLoadSummary.planning_run_id == planning_run_id)
                .order_by(VendorLoadSummary.vendor_id.asc())
            )
        )
        flow_blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc(), FlowBlocker.id.asc())
            )
        )

    assert [(row.vendor_id, row.vendor_recommended_jobs, row.status) for row in vendor_load] == [
        ("VEN-1", 1, "VENDOR_OVERLOADED"),
        ("VEN-2", 0, "OK"),
    ]
    assert ("VENDOR_OVERLOADED", None, None, None, "WARNING") in [
        (row.blocker_type, row.valve_id, row.component, row.operation_name, row.severity)
        for row in flow_blockers
    ]
    overloaded = next(row for row in flow_blockers if row.blocker_type == "VENDOR_OVERLOADED")
    assert "Vendor Vendor One recommended_jobs 1 reached modeled limit 1" in overloaded.cause
    assert "Review vendor Vendor One load and dispatch timing before release." in overloaded.recommended_action


def test_calculate_and_persist_placeholder_recommendations_persists_reason_codes_json_and_stable_refs(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_batch_subcontract_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.operation_name.asc(), Recommendation.id.asc())
            )
        )

    reason_codes_by_operation = {
        row.operation_name: json.loads(row.reason_codes_json)
        for row in recommendations
    }
    assert reason_codes_by_operation == {
        "HBM roughing": ["PRIMARY_OVERLOADED", "SUBCONTRACT_FEASIBLE", "BATCH_SUBCONTRACT_OPPORTUNITY"],
        "VTL finish": ["OK_INTERNAL"],
        "HBM finish": ["PRIMARY_OVERLOADED", "SUBCONTRACT_FEASIBLE", "BATCH_SUBCONTRACT_OPPORTUNITY"],
    }
    assert all(row.planned_operation_id is not None for row in recommendations)
    assert {(row.component, row.operation_name): row.component_line_no for row in recommendations} == {
        ("Body", "HBM roughing"): 1,
        ("Body", "VTL finish"): 1,
        ("Bonnet", "HBM finish"): 1,
    }


def test_calculate_and_persist_placeholder_recommendations_preserves_component_line_traceability_for_repeated_component_names(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_repeated_component_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        calculate_and_persist_placeholder_recommendations(planning_run_id=planning_run_id, db=session)

    with session_factory() as session:
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.planning_run_id == planning_run_id)
                .order_by(Recommendation.component_line_no.asc(), Recommendation.operation_name.asc(), Recommendation.id.asc())
            )
        )
        planned_operations = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.component_line_no.asc(), PlannedOperation.operation_no.asc())
            )
        )

    recommendation_refs = [
        (row.component_line_no, row.component, row.operation_name, row.planned_operation_id)
        for row in recommendations
        if row.component == "Body"
    ]
    planned_operation_ids = {
        (row.component_line_no, row.component, row.operation_name): row.id
        for row in planned_operations
        if row.component == "Body"
    }

    assert recommendation_refs == [
        (1, "Body", "HBM roughing", planned_operation_ids[(1, "Body", "HBM roughing")]),
        (1, "Body", "VTL finish", planned_operation_ids[(1, "Body", "VTL finish")]),
        (2, "Body", "HBM roughing", planned_operation_ids[(2, "Body", "HBM roughing")]),
        (2, "Body", "VTL finish", planned_operation_ids[(2, "Body", "VTL finish")]),
    ]


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


def _recommendation_workbook_rows() -> dict[str, list[list[object]]]:
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
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "Y", "HBM"]
    rows["Routing_Master"].append(["Body", 20, "VTL finish", "VTL", 4, "N", ""])
    rows["Routing_Master"].append(["Bonnet", 10, "HBM finish", "HBM", 8, "Y", "HBM"])

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
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 1, 0, "Medium", "A", "Y"]
    rows["Vendor_Master"].append(["VEN-2", "Vendor Two", "VTL", 2, 1, "Low", "B", "Y"])

    return rows


def _alternate_machine_workbook_rows() -> dict[str, list[list[object]]]:
    rows = _recommendation_workbook_rows()

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Alt_Machine",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
        "Vendor_Process",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", "VTL", 8, "Y", "HBM"]
    rows["Routing_Master"][2] = ["Body", 20, "VTL finish", "VTL", "", 4, "N", ""]
    rows["Routing_Master"][3] = ["Bonnet", 10, "HBM finish", "HBM", "", 8, "Y", "HBM"]

    return rows


def _alternate_machine_contention_workbook_rows() -> dict[str, list[list[object]]]:
    rows = _alternate_machine_workbook_rows()
    rows["Routing_Master"][3] = ["Bonnet", 10, "HBM finish", "HBM", "VTL", 8, "Y", "HBM"]
    rows["Machine_Master"][2] = ["VTL-1", "VTL", 8, 100, 2, "Y"]
    return rows


def _batch_subcontract_workbook_rows() -> dict[str, list[list[object]]]:
    rows = _recommendation_workbook_rows()
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 0, 0, "Medium", "A", "Y"]
    return rows


def _no_approved_vendor_workbook_rows() -> dict[str, list[list[object]]]:
    rows = _recommendation_workbook_rows()
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "Y", "EDM"]
    return rows


def _vendor_overload_workbook_rows() -> dict[str, list[list[object]]]:
    rows = _batch_subcontract_workbook_rows()
    rows["Routing_Master"].pop()
    rows["Component_Status"].pop()
    rows["Valve_Plan"].pop()
    rows["Machine_Master"][1] = ["HBM-1", "HBM", 8, 100, 0.5, "Y"]
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 0, 0, "Low", "A", "Y"]
    return rows


def _repeated_component_workbook_rows() -> dict[str, list[list[object]]]:
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
    rows["Component_Status"].append(["V-100", 2, "Body", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED"])

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
    rows["Routing_Master"].append(["Body", 20, "VTL finish", "VTL", 4, "N", ""])

    rows["Machine_Master"][0] = [
        "Machine_ID",
        "Machine_Type",
        "Hours_per_Day",
        "Efficiency_Percent",
        "Buffer_Days",
        "Active",
    ]
    rows["Machine_Master"][1] = ["HBM-1", "HBM", 8, 100, 5, "Y"]
    rows["Machine_Master"].append(["VTL-1", "VTL", 8, 100, 5, "Y"])

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


def _hold_for_priority_flow_workbook_rows() -> dict[str, list[list[object]]]:
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
