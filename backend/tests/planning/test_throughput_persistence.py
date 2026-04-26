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
from app.models.planning_run import PlanningRun, PlanningSnapshot
from app.models.output import ThroughputSummary
from app.planning.input_loader import PlanningSettingsOverride
from app.planning.throughput import ThroughputCalculationError
from app.services.machine_load import calculate_and_persist_machine_load
from app.services.throughput import calculate_and_persist_throughput_summary
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "throughput.sqlite3"
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


def test_calculate_and_persist_throughput_summary_uses_queue_updated_valve_readiness(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_throughput_workbook_rows()), planning_horizon_days=7)

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        summary = calculate_and_persist_throughput_summary(planning_run_id=planning_run_id, db=session)

    assert summary.target_throughput_value_cr == pytest.approx(2.5)
    assert summary.planned_throughput_value_cr == pytest.approx(1.75)
    assert summary.throughput_gap_cr == pytest.approx(0.75)
    assert summary.throughput_risk_flag is True

    with session_factory() as session:
        persisted = session.scalar(
            select(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id)
        )

    assert persisted is not None
    assert persisted.target_throughput_value_cr == pytest.approx(2.5)
    assert persisted.planned_throughput_value_cr == pytest.approx(1.75)
    assert persisted.throughput_gap_cr == pytest.approx(0.75)
    assert persisted.throughput_risk_flag == 1


def test_calculate_and_persist_throughput_summary_scales_target_for_fourteen_day_runs(client: TestClient) -> None:
    planning_run_id = _create_planning_run(
        client,
        workbook_bytes(sheets=_throughput_workbook_rows()),
        planning_horizon_days=14,
    )

    session_factory = create_session_factory()
    with session_factory() as session:
        calculate_and_persist_machine_load(planning_run_id=planning_run_id, db=session)
        summary = calculate_and_persist_throughput_summary(planning_run_id=planning_run_id, db=session)

    assert summary.target_throughput_value_cr == pytest.approx(5.0)
    assert summary.planned_throughput_value_cr == pytest.approx(1.75)
    assert summary.throughput_gap_cr == pytest.approx(3.25)
    assert summary.throughput_risk_flag is True


def test_calculate_and_persist_throughput_summary_honors_settings_override(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes(sheets=_throughput_workbook_rows()), planning_horizon_days=7)

    session_factory = create_session_factory()
    with session_factory() as session:
        settings_override = PlanningSettingsOverride(planning_horizon_days=14)
        calculate_and_persist_machine_load(
            planning_run_id=planning_run_id,
            db=session,
            settings_override=settings_override,
        )
        summary = calculate_and_persist_throughput_summary(
            planning_run_id=planning_run_id,
            db=session,
            settings_override=settings_override,
        )

    assert summary.target_throughput_value_cr == pytest.approx(5.0)
    assert summary.planned_throughput_value_cr == pytest.approx(1.75)
    assert summary.throughput_gap_cr == pytest.approx(3.25)
    assert summary.throughput_risk_flag is True

    with session_factory() as session:
        planning_run = session.get(PlanningRun, planning_run_id)
        snapshot = session.scalar(select(PlanningSnapshot).where(PlanningSnapshot.planning_run_id == planning_run_id))

    assert planning_run is not None
    assert planning_run.planning_horizon_days == 14
    assert snapshot is not None
    assert '"planning_horizon_days":14' in snapshot.snapshot_json


def test_calculate_and_persist_throughput_summary_requires_persisted_valve_readiness(client: TestClient) -> None:
    planning_run_id = _create_planning_run(client, workbook_bytes())

    session_factory = create_session_factory()
    with session_factory() as session:
        with pytest.raises(ThroughputCalculationError) as exc_info:
            calculate_and_persist_throughput_summary(planning_run_id=planning_run_id, db=session)

    assert exc_info.value.code == "VALVE_READINESS_MISSING"


def _create_planning_run(
    client: TestClient,
    workbook_content: bytes,
    *,
    planning_horizon_days: int = 7,
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
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": planning_horizon_days,
        },
    )
    assert planning_run_response.status_code == 201
    return str(planning_run_response.json()["id"])


def _throughput_workbook_rows() -> dict[str, list[list[object]]]:
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
