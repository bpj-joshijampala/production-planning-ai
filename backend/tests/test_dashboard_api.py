from collections.abc import Generator
from copy import deepcopy

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import FlowBlocker
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


def _create_calculated_run(client: TestClient, sheets: dict[str, list[list[object]]]) -> str:
    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
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

    calculate_response = client.post(f"/api/v1/planning-runs/{planning_run_response.json()['id']}/calculate")
    assert calculate_response.status_code == 200
    return str(planning_run_response.json()["id"])


def test_dashboard_and_throughput_endpoints_return_summary_tiles(client: TestClient) -> None:
    planning_run_id = _create_calculated_run(client, _dashboard_workbook_rows())

    dashboard_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/dashboard")
    throughput_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/throughput")

    assert dashboard_response.status_code == 200
    assert dashboard_response.json() == {
        "planning_run_id": planning_run_id,
        "active_valves": 2,
        "active_value_cr": 1.75,
        "planned_throughput_value_cr": 1.75,
        "throughput_gap_cr": 0.75,
        "overloaded_machines": 0,
        "underutilized_machines": 2,
        "flow_blockers": 1,
        "assembly_risk_valves": 1,
        "subcontract_recommendations": 0,
        "batch_risks": 1,
    }

    assert throughput_response.status_code == 200
    assert throughput_response.json() == {
        "planning_run_id": planning_run_id,
        "target_throughput_value_cr": 2.5,
        "planned_throughput_value_cr": 1.75,
        "throughput_gap_cr": 0.75,
        "throughput_risk_flag": True,
    }


def test_dashboard_table_endpoints_support_pagination_sort_and_filters(client: TestClient) -> None:
    planning_run_id = _create_calculated_run(client, _dashboard_workbook_rows())

    incoming = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"sort": "priority_score", "direction": "desc", "page": 1, "page_size": 1},
    )
    incoming_default = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"page": 1, "page_size": 10},
    )
    incoming_tied_page_1 = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"sort": "availability_date", "direction": "asc", "page": 1, "page_size": 1},
    )
    incoming_tied_page_2 = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"sort": "availability_date", "direction": "asc", "page": 2, "page_size": 1},
    )
    incoming_customer_filter = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"customer": "Beta", "page": 1, "page_size": 10},
    )
    incoming_valve_type_filter = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"valve_type": "Gate", "page": 1, "page_size": 10},
    )
    incoming_machine_type_filter = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"machine_type": "VTL", "page": 1, "page_size": 10},
    )
    incoming_date_window_filter = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/incoming-load",
        params={"availability_from": "2026-04-22", "availability_to": "2026-04-23", "page": 1, "page_size": 10},
    )
    machine_load_default = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/machine-load",
        params={"page": 1, "page_size": 10},
    )
    machine_load = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/machine-load",
        params={"status": "UNDERUTILIZED"},
    )
    queue = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/machine-load/HBM/queue",
        params={"sort": "sort_sequence", "direction": "asc", "page": 1, "page_size": 10},
    )
    queue_date_confidence = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/machine-load/HBM/queue",
        params={"date_confidence": "CONFIRMED", "page": 1, "page_size": 10},
    )
    queue_kit = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/machine-load/HBM/queue",
        params={"kit": "FULL_KIT_OR_NEAR_READY", "page": 1, "page_size": 10},
    )
    readiness = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/valve-readiness",
        params={"status": "AT_RISK"},
    )
    readiness_default = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/valve-readiness",
        params={"page": 1, "page_size": 10},
    )
    assembly_risk = client.get(f"/api/v1/planning-runs/{planning_run_id}/assembly-risk")
    blockers = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/flow-blockers",
        params={"blocker_type": "BATCH_RISK"},
    )

    assert incoming.status_code == 200
    incoming_payload = incoming.json()
    assert incoming_payload["total"] == 2
    assert incoming_payload["page_size"] == 1
    assert len(incoming_payload["items"]) == 1
    assert incoming_payload["items"][0]["machine_types"] == ["HBM", "VTL"]
    assert incoming_payload["items"][0]["valve_type"] == "Gate"
    assert incoming_payload["items"][0]["same_day_arrival_load_days"] == pytest.approx(2.0)
    assert incoming_payload["items"][0]["batch_risk_flag"] is True

    assert incoming_default.status_code == 200
    assert [row["valve_id"] for row in incoming_default.json()["items"]] == ["V-100", "V-200"]

    assert incoming_tied_page_1.status_code == 200
    assert incoming_tied_page_2.status_code == 200
    assert incoming_tied_page_1.json()["items"][0]["valve_id"] == "V-100"
    assert incoming_tied_page_2.json()["items"][0]["valve_id"] == "V-200"

    assert incoming_customer_filter.status_code == 200
    assert incoming_customer_filter.json()["total"] == 1
    assert incoming_customer_filter.json()["items"][0]["customer"] == "Beta"

    assert incoming_valve_type_filter.status_code == 200
    assert incoming_valve_type_filter.json()["total"] == 1
    assert incoming_valve_type_filter.json()["items"][0]["valve_type"] == "Gate"

    assert incoming_machine_type_filter.status_code == 200
    assert incoming_machine_type_filter.json()["total"] == 1
    assert incoming_machine_type_filter.json()["items"][0]["machine_types"] == ["HBM", "VTL"]

    assert incoming_date_window_filter.status_code == 200
    assert incoming_date_window_filter.json()["total"] == 0

    assert machine_load_default.status_code == 200
    assert [row["machine_type"] for row in machine_load_default.json()["items"]] == ["HBM", "VTL"]

    assert machine_load.status_code == 200
    assert machine_load.json()["total"] == 2
    assert all(row["status"] == "UNDERUTILIZED" for row in machine_load.json()["items"])

    assert queue.status_code == 200
    queue_payload = queue.json()
    assert queue_payload["machine_type"] == "HBM"
    assert "aggregated by machine type" in queue_payload["queue_approximation_warning"]
    assert [(row["component"], row["operation_name"]) for row in queue_payload["items"]] == [
        ("Body", "HBM roughing"),
        ("Bonnet", "HBM finish"),
    ]

    assert queue_date_confidence.status_code == 200
    assert queue_date_confidence.json()["total"] == 2
    assert all(row["date_confidence"] == "CONFIRMED" for row in queue_date_confidence.json()["items"])

    assert queue_kit.status_code == 200
    assert queue_kit.json()["total"] == 2

    assert readiness.status_code == 200
    assert readiness.json()["total"] == 1
    assert readiness.json()["items"][0]["valve_id"] == "V-100"

    assert readiness_default.status_code == 200
    assert readiness_default.json()["items"][0]["readiness_status"] == "AT_RISK"
    assert readiness_default.json()["items"][0]["valve_id"] == "V-100"

    assert assembly_risk.status_code == 200
    assert assembly_risk.json()["total"] == 1
    assert assembly_risk.json()["items"][0]["reason"] == "Assembly delay"

    assert blockers.status_code == 200
    assert blockers.json()["total"] == 1
    assert blockers.json()["items"][0]["blocker_type"] == "BATCH_RISK"
    assert blockers.json()["items"][0]["severity"] == "INFO"


def test_flow_blocker_severity_sort_uses_business_priority(client: TestClient) -> None:
    planning_run_id = _create_calculated_run(client, _dashboard_workbook_rows())

    session_factory = create_session_factory()
    with session_factory() as session:
        session.add_all(
            [
                FlowBlocker(
                    id="manual-critical-blocker",
                    planning_run_id=planning_run_id,
                    planned_operation_id=None,
                    valve_id=None,
                    component_line_no=None,
                    component=None,
                    operation_name=None,
                    blocker_type="MISSING_MACHINE",
                    cause="Missing machine capacity.",
                    recommended_action="Add active capacity.",
                    severity="CRITICAL",
                ),
                FlowBlocker(
                    id="manual-warning-blocker",
                    planning_run_id=planning_run_id,
                    planned_operation_id=None,
                    valve_id=None,
                    component_line_no=None,
                    component=None,
                    operation_name=None,
                    blocker_type="MACHINE_OVERLOAD",
                    cause="Machine load exceeds buffer.",
                    recommended_action="Rebalance queue.",
                    severity="WARNING",
                ),
            ]
        )
        session.commit()

    blockers = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/flow-blockers",
        params={"sort": "severity", "direction": "asc", "page": 1, "page_size": 10},
    )

    assert blockers.status_code == 200
    assert [row["severity"] for row in blockers.json()["items"]] == ["CRITICAL", "WARNING", "INFO"]


def test_component_status_endpoint_returns_next_operation_and_blockers(client: TestClient) -> None:
    planning_run_id = _create_calculated_run(client, _component_status_workbook_rows())

    component_status = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/component-status",
        params={"valve_id": "V-100"},
    )

    assert component_status.status_code == 200
    payload = component_status.json()
    assert payload["valve_id"] == "V-100"
    assert payload["total"] == 2
    assert payload["items"][0] == {
        "valve_id": "V-100",
        "customer": "Acme",
        "component_line_no": 1,
        "component": "Body",
        "current_location": "Stores",
        "fabrication_complete": True,
        "critical": True,
        "availability_date": "2026-04-21",
        "date_confidence": "CONFIRMED",
        "next_operation_name": "HBM roughing",
        "next_machine_type": "HBM",
        "internal_wait_days": 0.0,
        "status": "READY",
        "blocker_types": [],
        "blocker_summary": None,
    }
    assert payload["items"][1]["component"] == "Bonnet"
    assert payload["items"][1]["availability_date"] == "2026-04-30"
    assert payload["items"][1]["status"] == "BLOCKED"
    assert payload["items"][1]["blocker_types"] == ["MISSING_COMPONENT"]
    assert "outside planning horizon" in payload["items"][1]["blocker_summary"]


def test_assembly_risk_endpoint_orders_by_delay_then_assembly_date_then_value(client: TestClient) -> None:
    planning_run_id = _create_calculated_run(client, _assembly_risk_order_workbook_rows())

    assembly_risk = client.get(f"/api/v1/planning-runs/{planning_run_id}/assembly-risk")

    assert assembly_risk.status_code == 200
    payload = assembly_risk.json()
    assert [row["valve_id"] for row in payload["items"]] == ["V-200", "V-100", "V-300"]
    assert [row["assembly_delay_days"] for row in payload["items"]] == [3.0, 3.0, 1.0]
    assert payload["items"][0]["suggested_action"] == "Expedite missing components and rebalance the valve before assembly."


def test_recommendation_and_vendor_dashboard_endpoints_return_persisted_outputs(client: TestClient) -> None:
    planning_run_id = _create_calculated_run(client, _subcontract_dashboard_workbook_rows())

    recommendations_default = client.get(f"/api/v1/planning-runs/{planning_run_id}/subcontract-recommendations")
    recommendations = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/subcontract-recommendations",
        params={"recommendation_type": "SUBCONTRACT"},
    )
    vendor_load = client.get(f"/api/v1/planning-runs/{planning_run_id}/vendor-load")
    blockers = client.get(
        f"/api/v1/planning-runs/{planning_run_id}/flow-blockers",
        params={"blocker_type": "VENDOR_UNAVAILABLE"},
    )

    assert recommendations_default.status_code == 200
    default_payload = recommendations_default.json()
    assert default_payload["total"] == 3
    assert {row["recommendation_type"] for row in default_payload["items"]} == {
        "OK_INTERNAL",
        "SUBCONTRACT",
        "NO_FEASIBLE_OPTION",
    }

    assert recommendations.status_code == 200
    recommendation_payload = recommendations.json()
    assert recommendation_payload["total"] == 1
    assert recommendation_payload["items"][0]["recommendation_type"] == "SUBCONTRACT"
    assert recommendation_payload["items"][0]["suggested_vendor_id"] == "VEN-1"
    assert recommendation_payload["items"][0]["vendor_gain_days"] == 1.0
    assert recommendation_payload["items"][0]["reason_codes"] == ["PRIMARY_OVERLOADED", "SUBCONTRACT_FEASIBLE"]

    assert vendor_load.status_code == 200
    vendor_payload = vendor_load.json()
    assert vendor_payload["total"] == 1
    assert vendor_payload["items"][0]["vendor_id"] == "VEN-1"
    assert vendor_payload["items"][0]["vendor_recommended_jobs"] == 1
    assert "partially modeled in V1" in vendor_payload["items"][0]["limitation_warning"]

    assert blockers.status_code == 200
    blocker_payload = blockers.json()
    assert blocker_payload["total"] == 1
    assert blocker_payload["items"][0]["blocker_type"] == "VENDOR_UNAVAILABLE"
    assert blocker_payload["items"][0]["recommended_action"] == "Add an approved vendor for this process or keep the operation in-house with escalation."


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "dashboard_api.sqlite3"
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


def _dashboard_workbook_rows() -> dict[str, list[list[object]]]:
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
    ]
    rows["Valve_Plan"][1] = ["V-100", "O-100", "Acme", "Gate", "2026-05-01", "2026-04-22", 1.25, "A"]
    rows["Valve_Plan"].append(["V-200", "O-200", "Beta", "Globe", "2026-05-02", "2026-04-24", 0.5, "B"])

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


def _subcontract_dashboard_workbook_rows() -> dict[str, list[list[object]]]:
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


def _component_status_workbook_rows() -> dict[str, list[list[object]]]:
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
        "Current_Location",
    ]
    rows["Component_Status"][1] = ["V-100", 1, "Body", 1, "N", "Y", "2026-04-21", "Y", "CONFIRMED", "Stores"]
    rows["Component_Status"].append(["V-100", 2, "Bonnet", 1, "Y", "N", "2026-04-30", "Y", "EXPECTED", "Fabrication"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 8, "N"]
    rows["Routing_Master"].append(["Bonnet", 10, "VTL finish", "VTL", 4, "N"])

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


def _assembly_risk_order_workbook_rows() -> dict[str, list[list[object]]]:
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
    rows["Valve_Plan"].append(["V-200", "O-200", "Beta", "2026-05-01", "2026-04-22", 2.0, "A"])
    rows["Valve_Plan"].append(["V-300", "O-300", "Gamma", "2026-05-02", "2026-04-23", 0.75, "B"])

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
        "Current_Location",
    ]
    rows["Component_Status"][1] = ["V-100", 1, "Body", 1, "Y", "N", "2026-04-24", "Y", "EXPECTED", "Fabrication"]
    rows["Component_Status"].append(["V-200", 1, "Bonnet", 1, "Y", "N", "2026-04-24", "Y", "EXPECTED", "Fabrication"])
    rows["Component_Status"].append(["V-300", 1, "Disc", 1, "Y", "N", "2026-04-23", "Y", "EXPECTED", "Fabrication"])

    rows["Routing_Master"][0] = [
        "Component",
        "Operation_No",
        "Operation_Name",
        "Machine_Type",
        "Std_Total_Hrs",
        "Subcontract_Allowed",
    ]
    rows["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 2, "N"]
    rows["Routing_Master"].append(["Bonnet", 10, "VTL finish", "VTL", 2, "N"])
    rows["Routing_Master"].append(["Disc", 10, "Lathe turn", "Lathe", 2, "N"])

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
    rows["Machine_Master"].append(["LATHE-1", "Lathe", 8, 100, 5, "Y"])

    return rows
