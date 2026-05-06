import json
from pathlib import Path
from copy import deepcopy

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.exports.workbook import ExportSheet
from app.main import create_app
from app.models.output import MachineLoadSummary, ReportExport
from app.services.report_exports import generate_first_build_report_export, generate_xlsx_report_export
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    database_path = tmp_path / "report_exports_service.sqlite3"
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


def test_generate_xlsx_report_export_creates_workbook_and_audit_record(client: TestClient) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        machine_rows = [
            {
                "Machine_Type": row.machine_type,
                "Total_Operation_Hours": row.total_operation_hours,
                "Status": row.status,
            }
            for row in session.scalars(
                select(MachineLoadSummary)
                .where(MachineLoadSummary.planning_run_id == planning_run_id)
                .order_by(MachineLoadSummary.machine_type.asc())
            )
        ]
        report_export = generate_xlsx_report_export(
            planning_run_id=planning_run_id,
            report_type="MACHINE_LOAD",
            generated_by_user_id=DEV_USER_ID,
            sheets=(
                ExportSheet(
                    name="Machine_Load",
                    columns=("Machine_Type", "Total_Operation_Hours", "Status"),
                    rows=tuple(machine_rows),
                ),
            ),
            db=session,
        )

    export_path = Path(report_export.file_path)
    assert export_path.exists()
    assert report_export.file_format == "XLSX"
    assert report_export.generated_by_user_id == DEV_USER_ID

    metadata = json.loads(report_export.metadata_json or "{}")
    assert metadata == {
        "sheet_names": ["Machine_Load"],
        "sheet_row_counts": {"Machine_Load": 1},
    }

    workbook = load_workbook(export_path, data_only=True)
    assert workbook.sheetnames == ["Export_Info", "Machine_Load"]

    export_info_rows = {
        str(field): value
        for field, value in workbook["Export_Info"].iter_rows(min_row=2, values_only=True)
    }
    assert export_info_rows["Report_Type"] == "MACHINE_LOAD"
    assert export_info_rows["PlanningRun_ID"] == planning_run_id
    assert export_info_rows["Upload_File"] == "plan.xlsx"
    assert export_info_rows["Planning_Start_Date"] == "2026-04-21"
    assert export_info_rows["Planning_Horizon_Days"] == 7
    assert export_info_rows["Generated_At"] == report_export.generated_at
    assert export_info_rows["Generated_By"] == "Development Planner"

    machine_sheet = workbook["Machine_Load"]
    header = [cell.value for cell in machine_sheet[1]]
    first_row = [cell.value for cell in machine_sheet[2]]
    assert header == ["Machine_Type", "Total_Operation_Hours", "Status"]
    assert first_row == [
        machine_rows[0]["Machine_Type"],
        machine_rows[0]["Total_Operation_Hours"],
        machine_rows[0]["Status"],
    ]

    with session_factory() as session:
        persisted = session.get(ReportExport, report_export.id)

    assert persisted is not None
    assert persisted.report_type == "MACHINE_LOAD"
    assert persisted.file_path == str(export_path)


def test_generate_xlsx_report_export_removes_file_if_audit_write_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        machine_rows = [
            {
                "Machine_Type": row.machine_type,
                "Total_Operation_Hours": row.total_operation_hours,
                "Status": row.status,
            }
            for row in session.scalars(
                select(MachineLoadSummary)
                .where(MachineLoadSummary.planning_run_id == planning_run_id)
                .order_by(MachineLoadSummary.machine_type.asc())
            )
        ]

        def fail_commit() -> None:
            raise RuntimeError("audit commit failed")

        monkeypatch.setattr(session, "commit", fail_commit)

        export_dir = get_settings().export_dir / planning_run_id
        with pytest.raises(RuntimeError, match="audit commit failed"):
            generate_xlsx_report_export(
                planning_run_id=planning_run_id,
                report_type="MACHINE_LOAD",
                generated_by_user_id=DEV_USER_ID,
                sheets=(
                    ExportSheet(
                        name="Machine_Load",
                        columns=("Machine_Type", "Total_Operation_Hours", "Status"),
                        rows=tuple(machine_rows),
                    ),
                ),
                db=session,
            )

    assert not export_dir.exists() or not list(export_dir.glob("*.xlsx"))

    with session_factory() as session:
        export_count = session.scalar(
            select(func.count()).select_from(ReportExport).where(ReportExport.planning_run_id == planning_run_id)
        )

    assert export_count == 0


def test_generate_xlsx_report_export_rejects_non_calculated_run(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                "plan.xlsx",
                workbook_bytes(),
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
    planning_run_id = str(planning_run_response.json()["id"])

    session_factory = create_session_factory()
    with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            generate_xlsx_report_export(
                planning_run_id=planning_run_id,
                report_type="MACHINE_LOAD",
                generated_by_user_id=DEV_USER_ID,
                sheets=(
                    ExportSheet(
                        name="Machine_Load",
                        columns=("Machine_Type", "Total_Operation_Hours", "Status"),
                        rows=(),
                    ),
                ),
                db=session,
            )

    response = exc_info.value
    assert response.status_code == 409
    assert response.detail["code"] == "PLANNING_RUN_NOT_CALCULATED"


def test_generate_xlsx_report_export_removes_file_if_workbook_save_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)

    session_factory = create_session_factory()
    with session_factory() as session:
        machine_rows = [
            {
                "Machine_Type": row.machine_type,
                "Total_Operation_Hours": row.total_operation_hours,
                "Status": row.status,
            }
            for row in session.scalars(
                select(MachineLoadSummary)
                .where(MachineLoadSummary.planning_run_id == planning_run_id)
                .order_by(MachineLoadSummary.machine_type.asc())
            )
        ]

        def fail_save(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("workbook save failed")

        monkeypatch.setattr("app.exports.workbook.Workbook.save", fail_save)

        export_dir = get_settings().export_dir / planning_run_id
        with pytest.raises(RuntimeError, match="workbook save failed"):
            generate_xlsx_report_export(
                planning_run_id=planning_run_id,
                report_type="MACHINE_LOAD",
                generated_by_user_id=DEV_USER_ID,
                sheets=(
                    ExportSheet(
                        name="Machine_Load",
                        columns=("Machine_Type", "Total_Operation_Hours", "Status"),
                        rows=tuple(machine_rows),
                    ),
                ),
                db=session,
            )

    assert not export_dir.exists() or not list(export_dir.glob("*.xlsx"))

    with session_factory() as session:
        export_count = session.scalar(
            select(func.count()).select_from(ReportExport).where(ReportExport.planning_run_id == planning_run_id)
        )

    assert export_count == 0


def test_build_export_workbook_fails_on_missing_required_column() -> None:
    from app.exports.workbook import build_export_workbook

    with pytest.raises(ValueError, match="missing required columns: Status"):
        build_export_workbook(
            export_info_rows=(("Report_Type", "MACHINE_LOAD"),),
            sheets=(
                ExportSheet(
                    name="Machine_Load",
                    columns=("Machine_Type", "Status"),
                    rows=({"Machine_Type": "HBM"},),
                ),
            ),
        )


@pytest.mark.parametrize(
    ("report_type", "sheet_name", "expected_headers"),
    [
        (
            "MACHINE_LOAD",
            "Machine_Load",
            [
                "Machine_Type",
                "Total_Operation_Hours",
                "Capacity_Hours_Per_Day",
                "Load_Days",
                "Buffer_Days",
                "Overload_Flag",
                "Overload_Days",
                "Spare_Capacity_Days",
                "Underutilized_Flag",
                "Batch_Risk_Flag",
                "Status",
            ],
        ),
        (
            "SUBCONTRACT_PLAN",
            "Subcontract_Plan",
            [
                "Recommendation_Type",
                "Valve_ID",
                "Component_Line_No",
                "Component",
                "Operation_Name",
                "Machine_Type",
                "Suggested_Vendor_ID",
                "Suggested_Vendor_Name",
                "Internal_Wait_Days",
                "Internal_Completion_Days",
                "Vendor_Total_Days",
                "Vendor_Gain_Days",
                "Batch_Candidate_Count",
                "Batch_Opportunity",
                "Status",
                "Explanation",
            ],
        ),
        (
            "VALVE_READINESS",
            "Valve_Readiness",
            [
                "Valve_ID",
                "Customer",
                "Assembly_Date",
                "Dispatch_Date",
                "Value_Cr",
                "Total_Components",
                "Ready_Components",
                "Required_Components",
                "Ready_Required_Count",
                "Pending_Required_Count",
                "Full_Kit",
                "Near_Ready",
                "Expected_Completion_Date",
                "Assembly_Delay_Days",
                "Status",
                "Risk_Reason",
                "Valve_Flow_Gap_Days",
                "Valve_Flow_Imbalance",
            ],
        ),
        (
            "FLOW_BLOCKER",
            "Flow_Blockers",
            [
                "Severity",
                "Blocker_Type",
                "Valve_ID",
                "Component_Line_No",
                "Component",
                "Operation_Name",
                "Cause",
                "Recommended_Action",
            ],
        ),
        (
            "DAILY_EXECUTION",
            "Daily_Execution",
            [
                "Date",
                "Machine_Type",
                "Queue_Sequence",
                "Valve_ID",
                "Component_Line_No",
                "Component",
                "Operation_Name",
                "Planned_Action",
                "Internal_Wait_Days",
                "Internal_Completion_Date",
                "Extreme_Delay_Flag",
            ],
        ),
    ],
)
def test_generate_first_build_report_export_creates_expected_report_sheet(
    client: TestClient,
    report_type: str,
    sheet_name: str,
    expected_headers: list[str],
) -> None:
    planning_run_id = _create_calculated_planning_run(
        client,
        workbook_content=workbook_bytes(sheets=_first_build_export_workbook_rows()),
    )

    session_factory = create_session_factory()
    with session_factory() as session:
        report_export = generate_first_build_report_export(
            planning_run_id=planning_run_id,
            report_type=report_type,
            file_format="XLSX",
            db=session,
        )

    workbook = load_workbook(report_export.file_path, data_only=True)
    assert workbook.sheetnames == ["Export_Info", sheet_name]
    worksheet = workbook[sheet_name]
    assert [cell.value for cell in worksheet[1]] == expected_headers
    assert worksheet.max_row >= 2


def _create_calculated_planning_run(client: TestClient, workbook_content: bytes | None = None) -> str:
    upload_response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                "plan.xlsx",
                workbook_content if workbook_content is not None else workbook_bytes(),
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

    planning_run_id = str(planning_run_response.json()["id"])
    calculate_response = client.post(f"/api/v1/planning-runs/{planning_run_id}/calculate")
    assert calculate_response.status_code == 200
    return planning_run_id


def _first_build_export_workbook_rows() -> dict[str, list[list[object]]]:
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
    rows["Vendor_Master"][1] = ["VEN-1", "Vendor One", "HBM", 0, 0, "Medium", "A", "Y"]
    rows["Vendor_Master"].append(["VEN-2", "Vendor Two", "VTL", 2, 1, "Low", "B", "Y"])

    return rows
