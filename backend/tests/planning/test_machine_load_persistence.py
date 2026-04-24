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
from app.models.output import FlowBlocker, MachineLoadSummary, PlannedOperation, ValveReadinessSummary
from app.services.machine_load import calculate_and_persist_machine_load
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "machine_load.sqlite3"
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


def test_calculate_and_persist_machine_load_populates_queue_fields_and_machine_summaries(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_machine_load_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        result = calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)

    assert "aggregated by machine type" in result.queue_approximation_warning
    assert [row.blocker_type for row in result.flow_blockers] == ["BATCH_RISK"]

    with session_factory() as session:
        operations = list(
            session.scalars(
                select(PlannedOperation)
                .where(PlannedOperation.planning_run_id == planning_run_id)
                .order_by(PlannedOperation.sort_sequence.asc())
            )
        )
        summaries = list(
            session.scalars(
                select(MachineLoadSummary)
                .where(MachineLoadSummary.planning_run_id == planning_run_id)
                .order_by(MachineLoadSummary.machine_type.asc())
            )
        )
        readiness = list(
            session.scalars(
                select(ValveReadinessSummary)
                .where(ValveReadinessSummary.planning_run_id == planning_run_id)
                .order_by(ValveReadinessSummary.valve_id.asc())
            )
        )

    assert [(row.component, row.operation_no) for row in operations] == [
        ("Body", 10),
        ("Body", 20),
        ("Bonnet", 10),
    ]
    assert operations[0].internal_wait_days == pytest.approx(0.0)
    assert operations[0].processing_time_days == pytest.approx(1.0)
    assert operations[0].internal_completion_offset_days == pytest.approx(1.0)
    assert operations[1].operation_arrival_offset_days == pytest.approx(1.0)
    assert operations[1].processing_time_days == pytest.approx(0.5)
    assert operations[2].internal_wait_days == pytest.approx(1.0)
    assert operations[2].extreme_delay_flag == 0

    assert [(row.machine_type, row.status) for row in summaries] == [
        ("HBM", "UNDERUTILIZED"),
        ("VTL", "UNDERUTILIZED"),
    ]
    assert summaries[0].total_operation_hours == pytest.approx(16.0)
    assert summaries[0].load_days == pytest.approx(2.0)
    assert summaries[0].underutilized_flag == 1
    assert summaries[0].batch_risk_flag == 1
    assert summaries[1].total_operation_hours == pytest.approx(4.0)
    assert summaries[1].batch_risk_flag == 0
    assert [row.readiness_status for row in readiness] == ["AT_RISK", "READY"]
    assert [row.valve_expected_completion_date for row in readiness] == ["2026-04-23", "2026-04-23"]


def test_calculate_and_persist_machine_load_creates_missing_machine_blocker_and_data_incomplete_summary(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_missing_machine_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        result = calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)

    assert len(result.flow_blockers) == 1
    assert result.flow_blockers[0].blocker_type == "MISSING_MACHINE"

    with session_factory() as session:
        blocker = session.scalar(
            select(FlowBlocker)
            .where(FlowBlocker.planning_run_id == planning_run_id)
            .where(FlowBlocker.blocker_type == "MISSING_MACHINE")
        )
        operation = session.scalar(
            select(PlannedOperation)
            .where(PlannedOperation.planning_run_id == planning_run_id)
            .where(PlannedOperation.component == "Stem")
        )
        summary = session.scalar(
            select(MachineLoadSummary)
            .where(MachineLoadSummary.planning_run_id == planning_run_id)
            .where(MachineLoadSummary.machine_type == "Lathe")
        )

    assert blocker is not None
    assert blocker.component == "Stem"
    assert "Lathe" in blocker.cause
    assert operation is not None
    assert operation.operation_arrival_date is None
    assert operation.internal_completion_date is None
    assert summary is not None
    assert summary.capacity_hours_per_day == pytest.approx(0.0)
    assert summary.status == "DATA_INCOMPLETE"


def test_calculate_and_persist_machine_load_handles_all_routing_missing_as_blockers_instead_of_crashing(
    client: TestClient,
) -> None:
    rows = deepcopy(minimal_workbook_rows())
    rows["Routing_Master"] = [rows["Routing_Master"][0]]
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=rows))

    session_factory = create_session_factory()
    with session_factory() as session:
        result = calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)

    assert result.planned_operations == ()
    assert [row.blocker_type for row in result.flow_blockers] == ["MISSING_ROUTING"]

    with session_factory() as session:
        blockers = list(
            session.scalars(
                select(FlowBlocker)
                .where(FlowBlocker.planning_run_id == planning_run_id)
                .order_by(FlowBlocker.blocker_type.asc())
            )
        )
        summaries = list(
            session.scalars(
                select(MachineLoadSummary)
                .where(MachineLoadSummary.planning_run_id == planning_run_id)
                .order_by(MachineLoadSummary.machine_type.asc())
            )
        )
        readiness = list(
            session.scalars(
                select(ValveReadinessSummary)
                .where(ValveReadinessSummary.planning_run_id == planning_run_id)
                .order_by(ValveReadinessSummary.valve_id.asc())
            )
        )

    assert [(row.blocker_type, row.component) for row in blockers] == [("MISSING_ROUTING", "Body")]
    assert [(row.machine_type, row.status) for row in summaries] == [("HBM", "UNDERUTILIZED")]
    assert [row.readiness_status for row in readiness] == ["DATA_INCOMPLETE"]


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


def _machine_load_workbook_rows() -> dict[str, list[list[object]]]:
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


def _missing_machine_workbook_rows() -> dict[str, list[list[object]]]:
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
    rows["Component_Status"][1] = ["V-100", 1, "Stem", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED"]

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
    ]
    rows["Routing_Master"][1] = ["Stem", 10, "Lathe op", "Lathe", 4, "N"]

    rows["Machine_Master"][0] = [
        "Machine_ID",
        "Machine_Type",
        "Hours_per_Day",
        "Efficiency_Percent",
        "Buffer_Days",
        "Active",
    ]
    rows["Machine_Master"][1] = ["LATHE-1", "Lathe", 8, 100, 2, "N"]

    return rows
