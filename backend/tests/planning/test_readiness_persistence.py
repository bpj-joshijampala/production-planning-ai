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
from app.models.output import ValveReadinessSummary
from app.planning.readiness import ComponentKey
from app.services.valve_readiness import calculate_and_persist_valve_readiness
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "readiness_persistence.sqlite3"
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


def test_calculate_and_persist_valve_readiness_summaries_with_completion_offsets(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_readiness_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        summaries = calculate_and_persist_valve_readiness(
            planning_run_id=planning_run_id,
            db=session,
            component_completion_offsets={
                ComponentKey(valve_id="V-100", component_line_no=1): 8.0,
                ComponentKey(valve_id="V-050", component_line_no=1): 1.0,
                ComponentKey(valve_id="V-050", component_line_no=2): 3.0,
            },
        )

    assert len(summaries) == 2

    with session_factory() as session:
        persisted = list(
            session.scalars(
                select(ValveReadinessSummary)
                .where(ValveReadinessSummary.planning_run_id == planning_run_id)
                .order_by(ValveReadinessSummary.valve_id)
            )
        )

    assert len(persisted) == 2

    near_ready = persisted[0]
    at_risk = persisted[1]

    assert near_ready.valve_id == "V-050"
    assert near_ready.required_components == 2
    assert near_ready.pending_required_count == 1
    assert near_ready.full_kit_flag == 0
    assert near_ready.near_ready_flag == 1
    assert near_ready.readiness_status == "NEAR_READY"
    assert near_ready.risk_reason == "Missing component"
    assert near_ready.valve_expected_completion_date == "2026-04-24"

    assert at_risk.valve_id == "V-100"
    assert at_risk.otd_risk_flag == 1
    assert at_risk.otd_delay_days == 4
    assert at_risk.readiness_status == "AT_RISK"
    assert at_risk.risk_reason == "Missing component"
    assert at_risk.valve_expected_completion_date == "2026-04-29"


def test_calculate_and_persist_valve_readiness_defaults_routed_components_to_data_incomplete_without_offsets(
    client: TestClient,
) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_readiness_workbook_rows()))

    session_factory = create_session_factory()
    with session_factory() as session:
        summaries = calculate_and_persist_valve_readiness(planning_run_id=planning_run_id, db=session)

    assert [summary.readiness_status for summary in summaries] == ["DATA_INCOMPLETE", "DATA_INCOMPLETE"]

    with session_factory() as session:
        persisted_statuses = list(
            session.scalars(
                select(ValveReadinessSummary.readiness_status)
                .where(ValveReadinessSummary.planning_run_id == planning_run_id)
                .order_by(ValveReadinessSummary.valve_id)
            )
        )

    assert persisted_statuses == ["DATA_INCOMPLETE", "DATA_INCOMPLETE"]


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


def _readiness_workbook_rows() -> dict[str, list[list[object]]]:
    rows = deepcopy(minimal_workbook_rows())

    rows["Valve_Plan"][0] = [
        "Valve_ID",
        "Order_ID",
        "Customer",
        "Dispatch_Date",
        "Assembly_Date",
        "Value_Cr",
    ]
    rows["Valve_Plan"][1] = ["V-100", "O-100", "Acme", "2026-05-01", "2026-04-25", 1.25]
    rows["Valve_Plan"].append(["V-050", "O-050", "Beta", "2026-04-30", "2026-04-26", 0.75])

    rows["Component_Status"][0] = [
        "Valve_ID",
        "Component_Line_No",
        "Component",
        "Qty",
        "Fabrication_Required",
        "Fabrication_Complete",
        "Expected_Ready_Date",
        "Critical",
    ]
    rows["Component_Status"][1] = ["V-100", 1, "Body", 1, "Y", "N", "2026-04-29", "Y"]
    rows["Component_Status"].append(["V-050", 1, "Body", 1, "Y", "Y", "2026-04-22", "Y"])
    rows["Component_Status"].append(["V-050", 2, "Bonnet", 1, "Y", "N", "2026-04-24", "Y"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "Y"]
    rows["Routing_Master"].append(["Bonnet", 10, "HBM finish", "HBM", 4, "N"])

    return rows
