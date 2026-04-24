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
from app.models.output import IncomingLoadItem
from app.services.incoming_load import calculate_and_persist_incoming_load
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "priority_persistence.sqlite3"
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


def test_calculate_and_persist_incoming_load_items_prioritizes_and_filters_planned_components(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_priority_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        items = calculate_and_persist_incoming_load(planning_run_id=planning_run_id, db=session)

    assert [(row.valve_id, row.component, row.sort_sequence) for row in items] == [
        ("V-100", "Body", 1),
        ("V-200", "Bonnet", 2),
    ]

    with session_factory() as session:
        persisted = list(
            session.scalars(
                select(IncomingLoadItem)
                .where(IncomingLoadItem.planning_run_id == planning_run_id)
                .order_by(IncomingLoadItem.sort_sequence.asc())
            )
        )

    assert len(persisted) == 2

    first = persisted[0]
    second = persisted[1]

    assert first.valve_id == "V-100"
    assert first.component_line_no == 1
    assert first.current_ready_flag == 1
    assert first.availability_date == "2026-04-21"
    assert first.date_confidence == "CONFIRMED"
    assert first.priority_score == pytest.approx(1790.0)
    assert first.sort_sequence == 1
    assert json.loads(first.machine_types_json) == ["HBM", "VTL"]
    assert first.same_day_arrival_load_days is None
    assert first.batch_risk_flag == 0

    assert second.valve_id == "V-200"
    assert second.current_ready_flag == 0
    assert second.availability_date == "2026-04-25"
    assert second.date_confidence == "EXPECTED"
    assert second.priority_score == pytest.approx(1145.0)
    assert second.sort_sequence == 2
    assert json.loads(second.machine_types_json) == ["HBM"]


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


def _priority_workbook_rows() -> dict[str, list[list[object]]]:
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
    rows["Valve_Plan"].append(["V-300", "O-300", "Gamma", "2026-05-10", "2026-05-08", 0.40, "C"])

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
    rows["Component_Status"].append(["V-200", 1, "Bonnet", 1, "Y", "N", "2026-04-25", "Y", "EXPECTED"])
    rows["Component_Status"].append(["V-300", 1, "Stem", 1, "Y", "N", "2026-05-05", "Y", "TENTATIVE"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "Y"]
    rows["Routing_Master"].append(["Body", 20, "VTL finish", "VTL", 4, "N"])
    rows["Routing_Master"].append(["Bonnet", 10, "HBM finish", "HBM", 6, "N"])
    rows["Routing_Master"].append(["Stem", 10, "Lathe op", "Lathe", 3, "N"])

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
    rows["Machine_Master"].append(["LATHE-1", "Lathe", 16, 80, 2, "Y"])

    return rows
