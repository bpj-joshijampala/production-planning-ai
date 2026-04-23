from collections.abc import Generator
from copy import deepcopy
from datetime import date

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.planning_run import PlanningRun
from app.planning.input_loader import (
    PlanningInputError,
    PlanningSettingsOverride,
    build_planning_settings,
    load_planning_input,
)
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "planning_input_loader.sqlite3"
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


def test_load_planning_input_returns_ordered_canonical_records_and_run_settings(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_expanded_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_input = load_planning_input(planning_run_id=planning_run_id, db=session)

    assert planning_input.planning_run_id == planning_run_id
    assert planning_input.upload_batch_id
    assert planning_input.settings.planning_start_date == date(2026, 4, 21)
    assert planning_input.settings.planning_horizon_days == 14
    assert planning_input.settings.planning_end_date == date(2026, 5, 5)
    assert planning_input.settings.target_throughput_value_cr == pytest.approx(5.0)
    assert isinstance(planning_input.valves, tuple)
    assert isinstance(planning_input.component_statuses, tuple)
    assert isinstance(planning_input.routing_operations, tuple)
    assert isinstance(planning_input.machines, tuple)
    assert isinstance(planning_input.vendors, tuple)

    assert [valve.valve_id for valve in planning_input.valves] == ["V-050", "V-100"]
    assert planning_input.valves[0].dispatch_date == date(2026, 4, 30)
    assert planning_input.valves[0].assembly_date == date(2026, 4, 27)
    assert planning_input.valves[0].value_cr == pytest.approx(0.75)
    assert planning_input.valves[0].priority == "B"

    assert [(row.valve_id, row.component_line_no, row.component) for row in planning_input.component_statuses] == [
        ("V-050", 1, "Gate"),
        ("V-100", 1, "Body"),
    ]
    gate = planning_input.component_statuses[0]
    assert gate.fabrication_required is False
    assert gate.fabrication_complete is True
    assert gate.critical is True
    assert gate.priority_eligible is True
    assert gate.expected_ready_date == date(2026, 4, 22)
    assert gate.expected_from_fabrication is None
    assert gate.ready_date_type == "CONFIRMED"

    assert [(row.component, row.operation_no) for row in planning_input.routing_operations] == [
        ("Body", 10),
        ("Gate", 20),
    ]
    assert planning_input.routing_operations[0].subcontract_allowed is True
    assert planning_input.routing_operations[0].alt_machine == "VTL"

    assert [machine.machine_id for machine in planning_input.machines] == ["HBM-1", "HBM-2", "VTL-1"]
    assert planning_input.machines[0].active is True
    assert planning_input.machines[0].effective_hours_day == pytest.approx(12.8)

    assert [vendor.vendor_id for vendor in planning_input.vendors] == ["VEN-0", "VEN-1"]
    assert planning_input.vendors[0].approved is True
    assert planning_input.vendors[0].effective_lead_days == pytest.approx(2)


def test_load_planning_input_applies_settings_override_without_mutating_planning_run(client: TestClient) -> None:
    planning_run_id = _create_planning_run(
        client,
        workbook_bytes(),
        planning_start_date="2026-04-21",
        planning_horizon_days=7,
    )

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_input = load_planning_input(
            planning_run_id=planning_run_id,
            db=session,
            settings_override=PlanningSettingsOverride(
                planning_start_date=date(2026, 4, 23),
                planning_horizon_days=14,
            ),
        )
        planning_run = session.get(PlanningRun, planning_run_id)

    assert planning_input.settings.planning_start_date == date(2026, 4, 23)
    assert planning_input.settings.planning_horizon_days == 14
    assert planning_input.settings.planning_end_date == date(2026, 5, 7)
    assert planning_run is not None
    assert planning_run.planning_start_date == "2026-04-21"
    assert planning_run.planning_horizon_days == 7


def test_load_planning_input_collections_are_immutable(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes())

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_input = load_planning_input(planning_run_id=planning_run_id, db=session)

    with pytest.raises(AttributeError):
        planning_input.valves.append(planning_input.valves[0])  # type: ignore[attr-defined]


def test_build_planning_settings_defaults_to_seven_day_horizon_and_scales_target() -> None:
    settings = build_planning_settings(planning_start_date=date(2026, 4, 21))

    assert settings.planning_start_date == date(2026, 4, 21)
    assert settings.planning_horizon_days == 7
    assert settings.planning_end_date == date(2026, 4, 28)
    assert settings.target_throughput_value_cr == pytest.approx(2.5)


def test_build_planning_settings_rejects_unsupported_horizon() -> None:
    with pytest.raises(PlanningInputError) as exc_info:
        build_planning_settings(planning_start_date="2026-04-21", planning_horizon_days=30)

    assert exc_info.value.code == "INVALID_PLANNING_HORIZON"


def test_build_planning_settings_rejects_zero_instead_of_defaulting() -> None:
    with pytest.raises(PlanningInputError) as exc_info:
        build_planning_settings(planning_start_date="2026-04-21", planning_horizon_days=0)

    assert exc_info.value.code == "INVALID_PLANNING_HORIZON"


def test_load_planning_input_rejects_missing_planning_run(client: TestClient) -> None:
    session_factory = create_session_factory()
    with session_factory() as session:
        with pytest.raises(PlanningInputError) as exc_info:
            load_planning_input(planning_run_id="missing-run", db=session)

    assert exc_info.value.code == "PLANNING_RUN_NOT_FOUND"


def _create_planning_run(
    client: TestClient,
    workbook_content: bytes,
    *,
    planning_start_date: str = "2026-04-21",
    planning_horizon_days: int = 14,
) -> str:
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
            "planning_start_date": planning_start_date,
            "planning_horizon_days": planning_horizon_days,
        },
    )
    assert planning_run_response.status_code == 201
    return str(planning_run_response.json()["id"])


def _expanded_workbook_rows() -> dict[str, list[list[object]]]:
    rows = deepcopy(minimal_workbook_rows())

    rows["Valve_Plan"][0] = [
        "Valve_ID",
        "Order_ID",
        "Customer",
        "Valve_Type",
        "Dispatch_Date",
        "Assembly_Date",
        "Value_Cr",
        "Priority",
        "Status",
        "Remarks",
    ]
    rows["Valve_Plan"][1] = [
        "V-100",
        "O-100",
        "Acme",
        "Gate 10in",
        "2026-05-01",
        "2026-04-28",
        1.25,
        "A",
        "Planned",
        "First valve",
    ]
    rows["Valve_Plan"].append(
        [
            "V-050",
            "O-050",
            "Beta",
            "Gate 6in",
            "2026-04-30",
            "2026-04-27",
            0.75,
            "B",
            "Planned",
            "Second valve",
        ]
    )

    rows["Component_Status"][0] = [
        "Valve_ID",
        "Component_Line_No",
        "Component",
        "Qty",
        "Fabrication_Required",
        "Fabrication_Complete",
        "Expected_Ready_Date",
        "Critical",
        "Expected_From_Fabrication",
        "Priority_Eligible",
        "Ready_Date_Type",
        "Current_Location",
        "Comments",
    ]
    rows["Component_Status"][1] = [
        "V-100",
        "",
        "Body",
        1,
        "Y",
        "N",
        "2026-04-24",
        "Y",
        "2026-04-24",
        "N",
        "EXPECTED",
        "Fabrication",
        "Awaiting FCC",
    ]
    rows["Component_Status"].append(
        [
            "V-050",
            "",
            "Gate",
            2,
            "N",
            "Y",
            "2026-04-22",
            "Y",
            "",
            "Y",
            "CONFIRMED",
            "Stores",
            "Ready",
        ]
    )

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Alt_Machine",
        "Std_Setup_Hrs",
        "Std_Run_Hrs",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
        "Vendor_Process",
        "Notes",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", "VTL", 1, 7, 8, "Y", "HBM", "Primary route"]
    rows["Routing_Master"].append(["Gate", 20, "VTL finishing", "VTL", "", 0.5, 2.5, 3, "N", "", "Finish route"])

    rows["Machine_Master"][0] = [
        "Machine_ID",
        "Machine_Type",
        "Description",
        "Hours_per_Day",
        "Efficiency_Percent",
        "Shift_Pattern",
        "Buffer_Days",
        "Capability_Notes",
        "Active",
    ]
    rows["Machine_Master"][1] = ["HBM-1", "HBM", "Main HBM", 16, 80, "2 shift", 4, "Large body work", "Y"]
    rows["Machine_Master"].append(["HBM-2", "HBM", "Backup HBM", 8, 75, "1 shift", 4, "Smaller body work", "Y"])
    rows["Machine_Master"].append(["VTL-1", "VTL", "Main VTL", 16, 85, "2 shift", 3, "Gate work", "Y"])

    rows["Vendor_Master"][0] = [
        "Vendor_ID",
        "Vendor_Name",
        "Primary_Process",
        "Turnaround_Days",
        "Transport_Days_Total",
        "Capacity_Rating",
        "Reliability",
        "Approved",
        "Comments",
    ]
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 3, 1, "Medium", "A", "Y", "Approved HBM vendor"]
    rows["Vendor_Master"].append(["VEN-0", "Vendor Zero", "VTL", 1, 1, "Low", "B", "Y", "Approved VTL vendor"])

    return rows
