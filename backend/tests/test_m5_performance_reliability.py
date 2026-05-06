from collections.abc import Generator
from datetime import date, timedelta
from time import perf_counter

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
import pytest

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import MachineLoadSummary, PlannedOperation, Recommendation, ValveReadinessSummary
from tests.workbook_fixtures import workbook_bytes


DATASET_NAME = "generated_v1_volume_75_valves"
VALVE_COUNT = 75
COMPONENT_COUNT = VALVE_COUNT * 2
PLANNED_OPERATION_COUNT = VALVE_COUNT * 3
UPLOAD_VALIDATION_TARGET_SECONDS = 10.0
CALCULATION_TARGET_SECONDS = 3.0
DASHBOARD_TARGET_SECONDS = 1.0
EXPORT_TARGET_SECONDS = 10.0


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "m5_performance_reliability.sqlite3"
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


def test_v1_volume_upload_calculation_dashboard_and_export_meet_m5_e4_targets(client: TestClient) -> None:
    workbook_content = workbook_bytes(sheets=_v1_volume_workbook_rows(VALVE_COUNT))

    upload_start = perf_counter()
    upload_response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                f"{DATASET_NAME}.xlsx",
                workbook_content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    upload_seconds = perf_counter() - upload_start

    assert upload_response.status_code == 201
    upload_payload = upload_response.json()
    assert upload_payload["status"] == "VALIDATED"
    assert upload_payload["validation_error_count"] == 0
    assert upload_payload["validation_warning_count"] == 0
    assert upload_seconds < UPLOAD_VALIDATION_TARGET_SECONDS, _performance_message(
        "upload_validation",
        upload_seconds,
        UPLOAD_VALIDATION_TARGET_SECONDS,
    )

    planning_run_response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_payload["id"],
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )
    assert planning_run_response.status_code == 201
    planning_run_payload = planning_run_response.json()
    planning_run_id = planning_run_payload["id"]
    assert planning_run_payload["canonical_counts"] == {
        "valves": VALVE_COUNT,
        "component_statuses": COMPONENT_COUNT,
        "routing_operations": 3,
        "machines": 2,
        "vendors": 1,
    }

    calculation_start = perf_counter()
    calculation_response = client.post(f"/api/v1/planning-runs/{planning_run_id}/calculate")
    calculation_seconds = perf_counter() - calculation_start

    assert calculation_response.status_code == 200
    assert calculation_response.json()["status"] == "CALCULATED"
    assert calculation_seconds < CALCULATION_TARGET_SECONDS, _performance_message(
        "planning_calculation",
        calculation_seconds,
        CALCULATION_TARGET_SECONDS,
    )

    dashboard_start = perf_counter()
    dashboard_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/dashboard")
    dashboard_seconds = perf_counter() - dashboard_start

    assert dashboard_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    assert dashboard_payload["active_valves"] == VALVE_COUNT
    assert dashboard_seconds < DASHBOARD_TARGET_SECONDS, _performance_message(
        "dashboard_api",
        dashboard_seconds,
        DASHBOARD_TARGET_SECONDS,
    )

    export_start = perf_counter()
    export_response = client.post(
        f"/api/v1/planning-runs/{planning_run_id}/exports",
        json={"report_type": "DAILY_EXECUTION", "file_format": "XLSX"},
    )
    export_seconds = perf_counter() - export_start

    assert export_response.status_code == 201
    assert export_response.json()["metadata"]["sheet_row_counts"] == {
        "Daily_Execution": PLANNED_OPERATION_COUNT,
    }
    assert export_seconds < EXPORT_TARGET_SECONDS, _performance_message(
        "daily_execution_export",
        export_seconds,
        EXPORT_TARGET_SECONDS,
    )

    session_factory = create_session_factory()
    with session_factory() as session:
        planned_operation_count = session.scalar(
            select(func.count())
            .select_from(PlannedOperation)
            .where(PlannedOperation.planning_run_id == planning_run_id)
        )
        readiness_count = session.scalar(
            select(func.count())
            .select_from(ValveReadinessSummary)
            .where(ValveReadinessSummary.planning_run_id == planning_run_id)
        )
        machine_load_count = session.scalar(
            select(func.count())
            .select_from(MachineLoadSummary)
            .where(MachineLoadSummary.planning_run_id == planning_run_id)
        )
        recommendation_count = session.scalar(
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
        )

    assert planned_operation_count == PLANNED_OPERATION_COUNT
    assert readiness_count == VALVE_COUNT
    assert machine_load_count == 2
    assert recommendation_count == PLANNED_OPERATION_COUNT


def _v1_volume_workbook_rows(valve_count: int) -> dict[str, list[list[object]]]:
    planning_start = date(2026, 4, 21)
    rows: dict[str, list[list[object]]] = {
        "Valve_Plan": [
            [
                "Valve_ID",
                "Order_ID",
                "Customer",
                "Valve_Type",
                "Dispatch_Date",
                "Assembly_Date",
                "Value_Cr",
                "Priority",
                "Status",
            ]
        ],
        "Component_Status": [
            [
                "Valve_ID",
                "Component_Line_No",
                "Component",
                "Qty",
                "Fabrication_Required",
                "Fabrication_Complete",
                "Expected_Ready_Date",
                "Critical",
                "Ready_Date_Type",
                "Current_Location",
            ]
        ],
        "Routing_Master": [
            [
                "Component",
                "Operation_No",
                "Operation_Name",
                "Machine_Type",
                "Std_Total_Hrs",
                "Subcontract_Allowed",
                "Vendor_Process",
            ]
        ],
        "Machine_Master": [
            [
                "Machine_ID",
                "Machine_Type",
                "Description",
                "Hours_per_Day",
                "Efficiency_Percent",
                "Buffer_Days",
                "Active",
            ]
        ],
        "Vendor_Master": [
            [
                "Vendor_ID",
                "Vendor_Name",
                "Primary_Process",
                "Turnaround_Days",
                "Transport_Days_Total",
                "Capacity_Rating",
                "Reliability",
                "Approved",
            ]
        ],
    }

    for index in range(1, valve_count + 1):
        valve_id = f"V-{index:03d}"
        assembly_date = planning_start + timedelta(days=1 + (index % 7))
        dispatch_date = assembly_date + timedelta(days=7)
        rows["Valve_Plan"].append(
            [
                valve_id,
                f"O-{index:03d}",
                f"Customer {index % 5}",
                "Gate",
                dispatch_date.isoformat(),
                assembly_date.isoformat(),
                round(0.2 + (index % 10) * 0.05, 2),
                ("A", "B", "C")[index % 3],
                "ACTIVE",
            ]
        )
        rows["Component_Status"].append(
            [valve_id, 1, "Body", 1, "N", "Y", planning_start.isoformat(), "Y", "CONFIRMED", "Stores"]
        )
        rows["Component_Status"].append(
            [valve_id, 2, "Bonnet", 1, "N", "Y", planning_start.isoformat(), "Y", "CONFIRMED", "Stores"]
        )

    rows["Routing_Master"].extend(
        [
            ["Body", 10, "HBM roughing", "HBM", 2, "Y", "HBM"],
            ["Body", 20, "VTL finish", "VTL", 1, "N", ""],
            ["Bonnet", 10, "HBM finish", "HBM", 2, "Y", "HBM"],
        ]
    )
    rows["Machine_Master"].extend(
        [
            ["HBM-1", "HBM", "HBM pool", 16, 100, 30, "Y"],
            ["VTL-1", "VTL", "VTL pool", 16, 100, 30, "Y"],
        ]
    )
    rows["Vendor_Master"].append(["VEN-1", "Vendor One", "HBM", 2, 1, "High", "A", "Y"])
    return rows


def _performance_message(metric: str, actual_seconds: float, target_seconds: float) -> str:
    return (
        f"{metric} exceeded M5-E4 target for dataset={DATASET_NAME}, "
        f"valves={VALVE_COUNT}, components={COMPONENT_COUNT}, "
        f"planned_operations={PLANNED_OPERATION_COUNT}: "
        f"actual={actual_seconds:.3f}s target={target_seconds:.3f}s"
    )
