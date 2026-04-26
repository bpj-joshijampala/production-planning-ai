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
from app.models.output import PlannedOperation, Recommendation, VendorLoadSummary
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
        ("Body", "HBM roughing"): "MACHINE_OVERLOAD",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "MACHINE_OVERLOAD",
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
        (row.component, row.operation_name): row.recommendation_type
        for row in recommendations
    } == {
        ("Body", "HBM roughing"): "MACHINE_OVERLOAD",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "MACHINE_OVERLOAD",
    }
    assert {
        (row.component, row.operation_name): row.recommendation_status
        for row in planned_operations
    } == {
        ("Body", "HBM roughing"): "MACHINE_OVERLOAD",
        ("Body", "VTL finish"): "OK_INTERNAL",
        ("Bonnet", "HBM finish"): "MACHINE_OVERLOAD",
    }
    assert [(row.vendor_id, row.vendor_recommended_jobs, row.status) for row in vendor_load] == [
        ("VEN-1", 0, "OK"),
        ("VEN-2", 0, "OK"),
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
    rows["Routing_Master"].append(["Bonnet", 10, "HBM finish", "HBM", 8, "N", ""])

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
        "Approved",
    ]
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 3, 1, "Medium", "Y"]
    rows["Vendor_Master"].append(["VEN-2", "Vendor Two", "VTL", 2, 1, "Low", "Y"])

    return rows
