from contextlib import suppress
from pathlib import Path
import json
import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.exports.workbook import ExportSheet, build_export_workbook
from app.models.output import (
    FlowBlocker,
    MachineLoadSummary,
    PlannedOperation,
    Recommendation,
    ReportExport,
    ValveReadinessSummary,
)
from app.models.planning_run import PlanningRun
from app.models.upload import UploadBatch
from app.models.user import User


ALLOWED_REPORT_TYPES = {
    "MACHINE_LOAD",
    "SUBCONTRACT_PLAN",
    "VALVE_READINESS",
    "FLOW_BLOCKER",
    "WEEKLY_PLANNING",
    "DAILY_EXECUTION",
    "A3_PLANNING",
}
SUPPORTED_FILE_FORMAT = "XLSX"
DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
logger = logging.getLogger(__name__)


def generate_xlsx_report_export(
    *,
    planning_run_id: str,
    report_type: str,
    generated_by_user_id: str,
    sheets: tuple[ExportSheet, ...],
    db: Session,
) -> ReportExport:
    if report_type not in ALLOWED_REPORT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "UNSUPPORTED_REPORT_TYPE", "message": f"Unsupported report type {report_type}."},
        )

    planning_run = _load_planning_run(planning_run_id=planning_run_id, db=db)
    _ensure_planning_run_is_calculated(planning_run)
    upload_batch = _load_upload_batch(upload_batch_id=planning_run.upload_batch_id, db=db)
    generated_by_user = _load_user(user_id=generated_by_user_id, db=db)

    generated_at = utc_now_iso()
    export_dir = get_settings().export_dir / planning_run_id
    export_dir.mkdir(parents=True, exist_ok=True)

    file_path = export_dir / _build_export_filename(report_type=report_type, generated_at=generated_at)
    audit_committed = False

    try:
        workbook = build_export_workbook(
            export_info_rows=_build_export_info_rows(
                planning_run=planning_run,
                upload_batch=upload_batch,
                report_type=report_type,
                generated_at=generated_at,
                generated_by_user=generated_by_user,
            ),
            sheets=sheets,
        )
        workbook.save(file_path)

        report_export = ReportExport(
            id=new_uuid(),
            planning_run_id=planning_run_id,
            report_type=report_type,
            file_path=str(file_path),
            file_format=SUPPORTED_FILE_FORMAT,
            generated_by_user_id=generated_by_user.id,
            generated_at=generated_at,
            metadata_json=json.dumps(
                {
                    "sheet_names": [sheet.name for sheet in sheets],
                    "sheet_row_counts": {sheet.name: len(sheet.rows) for sheet in sheets},
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ),
        )
        db.add(report_export)
        db.commit()
        audit_committed = True
        db.refresh(report_export)
    except Exception:
        db.rollback()
        if not audit_committed:
            _remove_generated_export(file_path=file_path, export_dir=export_dir)
        logger.exception("Report export generation failed planning_run_id=%s report_type=%s", planning_run_id, report_type)
        raise

    return report_export


def generate_first_build_report_export(
    *,
    planning_run_id: str,
    report_type: str,
    file_format: str,
    db: Session,
    generated_by_user_id: str = DEV_USER_ID,
) -> ReportExport:
    normalized_file_format = file_format.strip().upper()
    if normalized_file_format != SUPPORTED_FILE_FORMAT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_EXPORT_FORMAT",
                "message": f"Unsupported export format {file_format}. Only XLSX is supported in V1.",
            },
        )

    sheets = _build_first_usable_report_sheets(planning_run_id=planning_run_id, report_type=report_type, db=db)
    return generate_xlsx_report_export(
        planning_run_id=planning_run_id,
        report_type=report_type,
        generated_by_user_id=generated_by_user_id,
        sheets=sheets,
        db=db,
    )


def get_report_export(report_export_id: str, db: Session) -> ReportExport:
    report_export = db.get(ReportExport, report_export_id)
    if report_export is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_EXPORT_NOT_FOUND", "message": f"Report export {report_export_id} was not found."},
        )
    return report_export


def list_report_exports(
    *,
    planning_run_id: str,
    db: Session,
    page: int,
    page_size: int,
    latest_only: bool = False,
) -> tuple[list[ReportExport], int]:
    _load_planning_run(planning_run_id=planning_run_id, db=db)

    query = (
        select(ReportExport)
        .where(ReportExport.planning_run_id == planning_run_id)
        .order_by(ReportExport.generated_at.desc(), ReportExport.id.desc())
    )
    if latest_only:
        rows = list(db.scalars(query))
        latest_by_type: list[ReportExport] = []
        seen_report_types: set[str] = set()
        for row in rows:
            if row.report_type in seen_report_types:
                continue
            latest_by_type.append(row)
            seen_report_types.add(row.report_type)

        total = len(latest_by_type)
        offset = (page - 1) * page_size
        return latest_by_type[offset : offset + page_size], total

    total = (
        db.scalar(
            select(func.count())
            .select_from(ReportExport)
            .where(ReportExport.planning_run_id == planning_run_id)
        )
        or 0
    )
    rows = list(db.scalars(query.offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def resolve_report_export_download(report_export_id: str, db: Session) -> tuple[ReportExport, Path]:
    report_export = get_report_export(report_export_id, db)
    file_path = Path(report_export.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REPORT_EXPORT_FILE_MISSING",
                "message": f"Generated file for report export {report_export_id} was not found.",
            },
        )
    return report_export, file_path


def _build_export_filename(*, report_type: str, generated_at: str) -> str:
    safe_timestamp = generated_at.replace("-", "").replace(":", "").replace(".", "")
    return f"{report_type.lower()}_{safe_timestamp}.xlsx"


def _build_export_info_rows(
    *,
    planning_run: PlanningRun,
    upload_batch: UploadBatch,
    report_type: str,
    generated_at: str,
    generated_by_user: User,
) -> tuple[tuple[str, object | None], ...]:
    return (
        ("Report_Type", report_type),
        ("PlanningRun_ID", planning_run.id),
        ("Upload_File", upload_batch.original_filename),
        ("Planning_Start_Date", planning_run.planning_start_date),
        ("Planning_Horizon_Days", planning_run.planning_horizon_days),
        ("Generated_At", generated_at),
        ("Generated_By", generated_by_user.display_name),
    )


def _build_first_usable_report_sheets(
    *,
    planning_run_id: str,
    report_type: str,
    db: Session,
) -> tuple[ExportSheet, ...]:
    if report_type == "MACHINE_LOAD":
        return (_build_machine_load_sheet(planning_run_id=planning_run_id, db=db),)
    if report_type == "SUBCONTRACT_PLAN":
        return (_build_subcontract_plan_sheet(planning_run_id=planning_run_id, db=db),)
    if report_type == "VALVE_READINESS":
        return (_build_valve_readiness_sheet(planning_run_id=planning_run_id, db=db),)
    if report_type == "FLOW_BLOCKER":
        return (_build_flow_blocker_sheet(planning_run_id=planning_run_id, db=db),)
    if report_type == "DAILY_EXECUTION":
        return (_build_daily_execution_sheet(planning_run_id=planning_run_id, db=db),)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "UNSUPPORTED_REPORT_TYPE", "message": f"Unsupported report type {report_type}."},
    )


def _build_machine_load_sheet(*, planning_run_id: str, db: Session) -> ExportSheet:
    rows = list(
        db.scalars(
            select(MachineLoadSummary)
            .where(MachineLoadSummary.planning_run_id == planning_run_id)
            .order_by(MachineLoadSummary.machine_type.asc(), MachineLoadSummary.id.asc())
        )
    )
    return ExportSheet(
        name="Machine_Load",
        columns=(
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
        ),
        rows=tuple(
            {
                "Machine_Type": row.machine_type,
                "Total_Operation_Hours": row.total_operation_hours,
                "Capacity_Hours_Per_Day": row.capacity_hours_per_day,
                "Load_Days": row.load_days,
                "Buffer_Days": row.buffer_days,
                "Overload_Flag": row.overload_flag,
                "Overload_Days": row.overload_days,
                "Spare_Capacity_Days": row.spare_capacity_days,
                "Underutilized_Flag": row.underutilized_flag,
                "Batch_Risk_Flag": row.batch_risk_flag,
                "Status": row.status,
            }
            for row in rows
        ),
    )


def _build_subcontract_plan_sheet(*, planning_run_id: str, db: Session) -> ExportSheet:
    rows = list(
        db.scalars(
            select(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
            .where(
                Recommendation.recommendation_type.in_(
                    ("SUBCONTRACT", "BATCH_SUBCONTRACT_OPPORTUNITY")
                )
            )
            .order_by(
                Recommendation.suggested_vendor_id.asc(),
                Recommendation.valve_id.asc(),
                Recommendation.component_line_no.asc(),
                Recommendation.operation_name.asc(),
                Recommendation.id.asc(),
            )
        )
    )
    return ExportSheet(
        name="Subcontract_Plan",
        columns=(
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
        ),
        rows=tuple(
            {
                "Recommendation_Type": row.recommendation_type,
                "Valve_ID": row.valve_id,
                "Component_Line_No": row.component_line_no,
                "Component": row.component,
                "Operation_Name": row.operation_name,
                "Machine_Type": row.machine_type,
                "Suggested_Vendor_ID": row.suggested_vendor_id,
                "Suggested_Vendor_Name": row.suggested_vendor_name,
                "Internal_Wait_Days": row.internal_wait_days,
                "Internal_Completion_Days": row.internal_completion_days,
                "Vendor_Total_Days": row.vendor_total_days,
                "Vendor_Gain_Days": row.vendor_gain_days,
                "Batch_Candidate_Count": row.subcontract_batch_candidate_count,
                "Batch_Opportunity": row.batch_subcontract_opportunity_flag,
                "Status": row.status,
                "Explanation": row.explanation,
            }
            for row in rows
        ),
    )


def _build_valve_readiness_sheet(*, planning_run_id: str, db: Session) -> ExportSheet:
    rows = list(
        db.scalars(
            select(ValveReadinessSummary)
            .where(ValveReadinessSummary.planning_run_id == planning_run_id)
            .order_by(ValveReadinessSummary.assembly_date.asc(), ValveReadinessSummary.valve_id.asc())
        )
    )
    return ExportSheet(
        name="Valve_Readiness",
        columns=(
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
        ),
        rows=tuple(
            {
                "Valve_ID": row.valve_id,
                "Customer": row.customer,
                "Assembly_Date": row.assembly_date,
                "Dispatch_Date": row.dispatch_date,
                "Value_Cr": row.value_cr,
                "Total_Components": row.total_components,
                "Ready_Components": row.ready_components,
                "Required_Components": row.required_components,
                "Ready_Required_Count": row.ready_required_count,
                "Pending_Required_Count": row.pending_required_count,
                "Full_Kit": row.full_kit_flag,
                "Near_Ready": row.near_ready_flag,
                "Expected_Completion_Date": row.valve_expected_completion_date,
                "Assembly_Delay_Days": row.otd_delay_days,
                "Status": row.readiness_status,
                "Risk_Reason": row.risk_reason,
                "Valve_Flow_Gap_Days": row.valve_flow_gap_days,
                "Valve_Flow_Imbalance": row.valve_flow_imbalance_flag,
            }
            for row in rows
        ),
    )


def _build_flow_blocker_sheet(*, planning_run_id: str, db: Session) -> ExportSheet:
    severity_rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    rows = list(
        db.scalars(select(FlowBlocker).where(FlowBlocker.planning_run_id == planning_run_id))
    )
    rows.sort(
        key=lambda row: (
            severity_rank.get(row.severity, 99),
            row.blocker_type or "",
            row.valve_id or "",
            row.component_line_no or 0,
            row.operation_name or "",
            row.id,
        )
    )
    return ExportSheet(
        name="Flow_Blockers",
        columns=(
            "Severity",
            "Blocker_Type",
            "Valve_ID",
            "Component_Line_No",
            "Component",
            "Operation_Name",
            "Cause",
            "Recommended_Action",
        ),
        rows=tuple(
            {
                "Severity": row.severity,
                "Blocker_Type": row.blocker_type,
                "Valve_ID": row.valve_id,
                "Component_Line_No": row.component_line_no,
                "Component": row.component,
                "Operation_Name": row.operation_name,
                "Cause": row.cause,
                "Recommended_Action": row.recommended_action,
            }
            for row in rows
        ),
    )


def _build_daily_execution_sheet(*, planning_run_id: str, db: Session) -> ExportSheet:
    operations = list(
        db.scalars(select(PlannedOperation).where(PlannedOperation.planning_run_id == planning_run_id))
    )
    operations.sort(
        key=lambda row: (
            row.internal_completion_date is None,
            row.internal_completion_date or "",
            row.sort_sequence,
            row.id,
        )
    )
    stable_recommendation_type_by_operation_id: dict[str, str] = {}
    for row in db.scalars(
        select(Recommendation)
        .where(Recommendation.planning_run_id == planning_run_id)
        .where(Recommendation.planned_operation_id.is_not(None))
        .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
    ):
        if row.planned_operation_id is not None and row.planned_operation_id not in stable_recommendation_type_by_operation_id:
            stable_recommendation_type_by_operation_id[row.planned_operation_id] = row.recommendation_type

    return ExportSheet(
        name="Daily_Execution",
        columns=(
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
        ),
        rows=tuple(
            {
                "Date": row.operation_arrival_date,
                "Machine_Type": row.machine_type,
                "Queue_Sequence": row.sort_sequence,
                "Valve_ID": row.valve_id,
                "Component_Line_No": row.component_line_no,
                "Component": row.component,
                "Operation_Name": row.operation_name,
                "Planned_Action": stable_recommendation_type_by_operation_id.get(row.id, "OK_INTERNAL"),
                "Internal_Wait_Days": row.internal_wait_days,
                "Internal_Completion_Date": row.internal_completion_date,
                "Extreme_Delay_Flag": row.extreme_delay_flag,
            }
            for row in operations
        ),
    )


def _load_planning_run(*, planning_run_id: str, db: Session) -> PlanningRun:
    planning_run = db.get(PlanningRun, planning_run_id)
    if planning_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLANNING_RUN_NOT_FOUND", "message": f"PlanningRun {planning_run_id} was not found."},
        )
    return planning_run


def _ensure_planning_run_is_calculated(planning_run: PlanningRun) -> None:
    if planning_run.status != "CALCULATED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PLANNING_RUN_NOT_CALCULATED",
                "message": f"PlanningRun {planning_run.id} must be CALCULATED before export generation.",
            },
        )


def _load_upload_batch(*, upload_batch_id: str, db: Session) -> UploadBatch:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_NOT_FOUND", "message": f"Upload {upload_batch_id} was not found."},
        )
    return upload_batch


def _load_user(*, user_id: str, db: Session) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"User {user_id} was not found."},
        )
    return user


def _remove_generated_export(*, file_path: Path, export_dir: Path) -> None:
    with suppress(FileNotFoundError):
        file_path.unlink()
    with suppress(OSError):
        export_dir.rmdir()
