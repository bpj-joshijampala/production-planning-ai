from collections.abc import Generator
from copy import deepcopy

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import FlowBlocker, PlannedOperation
from app.services.planned_operations import calculate_and_persist_planned_operations
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "planned_operations.sqlite3"
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


def test_calculate_and_persist_planned_operations_expands_sorted_routing_rows(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_routing_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        expansion = calculate_and_persist_planned_operations(planning_run_id=planning_run_id, db=session)

    assert len(expansion.planned_operations) == 3
    assert expansion.flow_blockers == ()

    with session_factory() as session:
        persisted = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc())
            )
        )

    assert [(row.component, row.operation_no, row.sort_sequence) for row in persisted] == [
        ("Body", 10, 1),
        ("Body", 20, 2),
        ("Bonnet", 10, 3),
    ]
    assert [row.operation_hours for row in persisted] == [10.0, 6.0, 2.0]
    assert [row.operation_arrival_date for row in persisted] == [None, None, None]
    assert all(row.internal_wait_days is None for row in persisted)


def test_calculate_and_persist_planned_operations_creates_missing_routing_blocker_from_warning_only_upload(
    client: TestClient,
) -> None:
    session_factory = create_session_factory()
    upload_response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                "missing-routing.xlsx",
                workbook_bytes(sheets=_routing_workbook_rows_missing_body_routing()),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_response.status_code == 201
    upload_payload = upload_response.json()
    assert upload_payload["status"] == "VALIDATED"
    assert upload_payload["validation_warning_count"] == 1

    planning_run_id = _create_planning_run_from_upload_id(client, str(upload_payload["id"]))
    with session_factory() as session:
        expansion = calculate_and_persist_planned_operations(planning_run_id=planning_run_id, db=session)

    assert [(row.component, row.operation_no) for row in expansion.planned_operations] == [("Bonnet", 10)]
    assert len(expansion.flow_blockers) == 1
    assert expansion.flow_blockers[0].blocker_type == "MISSING_ROUTING"

    with session_factory() as session:
        blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.component.asc())
            )
        )
        operations = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc())
            )
        )

    assert [(row.component, row.blocker_type, row.severity) for row in blockers] == [
        ("Body", "MISSING_ROUTING", "CRITICAL"),
    ]
    assert [(row.component, row.operation_no) for row in operations] == [("Bonnet", 10)]


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
    return _create_planning_run_from_upload_id(client, str(upload_response.json()["id"]))


def _create_planning_run_from_upload_id(client: TestClient, upload_id: str) -> str:
    planning_run_response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_id,
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )
    assert planning_run_response.status_code == 201
    return str(planning_run_response.json()["id"])


def _routing_workbook_rows() -> dict[str, list[list[object]]]:
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
    rows["Valve_Plan"].append(["V-200", "O-200", "Beta", "2026-05-02", "2026-04-24", 0.50, "B"])

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
    rows["Component_Status"][1] = ["V-100", 1, "Body", 2, "N", "Y", "2026-04-21", "Y", "CONFIRMED"]
    rows["Component_Status"].append(["V-200", 1, "Bonnet", 1, "Y", "N", "2026-04-24", "Y", "EXPECTED"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Setup_Hrs",
        "Std_Run_Hrs",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
    ]
    rows["Routing_Master"][1] = ["Body", 20, "VTL finish", "VTL", 1, 2, 3, "N"]
    rows["Routing_Master"].append(["Body", 10, "HBM roughing", "HBM", 2, 3, 5, "Y"])
    rows["Routing_Master"].append(["Bonnet", 10, "HBM finish", "HBM", 0.5, 1.5, 2, "N"])

    rows["Machine_Master"][0] = [
        "Machine_ID",
        "Machine_Type",
        "Hours_per_Day",
        "Efficiency_Percent",
        "Buffer_Days",
        "Active",
    ]
    rows["Machine_Master"][1] = ["HBM-1", "HBM", 16, 80, 4, "Y"]
    rows["Machine_Master"].append(["VTL-1", "VTL", 16, 80, 3, "Y"])

    return rows


def _routing_workbook_rows_missing_body_routing() -> dict[str, list[list[object]]]:
    rows = _routing_workbook_rows()
    rows["Routing_Master"] = [rows["Routing_Master"][0], rows["Routing_Master"][3]]
    return rows
