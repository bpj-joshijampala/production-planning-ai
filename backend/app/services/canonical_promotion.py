from collections import defaultdict
from dataclasses import dataclass
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.canonical import ComponentStatus, Machine, RoutingOperation, Valve, Vendor
from app.models.planning_run import PlanningRun
from app.models.upload import ImportStagingRow, ImportValidationIssue, UploadBatch


@dataclass(frozen=True)
class PromotionResult:
    upload_batch_id: str
    planning_run_id: str
    valves: int
    component_statuses: int
    routing_operations: int
    machines: int
    vendors: int


class PromotionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def promote_upload_to_canonical(
    upload_batch_id: str, planning_run_id: str, db: Session, *, commit: bool = True
) -> PromotionResult:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None:
        raise PromotionError("UPLOAD_NOT_FOUND", f"Upload {upload_batch_id} was not found.")

    planning_run = db.get(PlanningRun, planning_run_id)
    if planning_run is None:
        raise PromotionError("PLANNING_RUN_NOT_FOUND", f"PlanningRun {planning_run_id} was not found.")
    if planning_run.upload_batch_id != upload_batch_id:
        raise PromotionError(
            "PLANNING_RUN_UPLOAD_MISMATCH",
            f"PlanningRun {planning_run_id} does not belong to upload {upload_batch_id}.",
        )

    blocking_issue_count = db.scalar(
        select(func.count())
        .select_from(ImportValidationIssue)
        .where(ImportValidationIssue.upload_batch_id == upload_batch_id)
        .where(ImportValidationIssue.severity == "BLOCKING")
    )
    if upload_batch.validation_error_count > 0 or blocking_issue_count:
        raise PromotionError("VALIDATION_BLOCKED", f"Upload {upload_batch_id} has blocking validation issues.")

    existing_valves = db.scalar(select(func.count()).select_from(Valve).where(Valve.planning_run_id == planning_run_id))
    if existing_valves:
        raise PromotionError("CANONICAL_ALREADY_PROMOTED", f"PlanningRun {planning_run_id} already has canonical rows.")

    rows_by_sheet = _load_staging_payloads(upload_batch_id, db)
    valves = [_to_valve(planning_run_id, payload) for payload in rows_by_sheet["Valve_Plan"]]
    component_statuses = [
        _to_component_status(planning_run_id, payload) for payload in rows_by_sheet["Component_Status"]
    ]
    routing_operations = [
        _to_routing_operation(planning_run_id, payload) for payload in rows_by_sheet["Routing_Master"]
    ]
    machines = [_to_machine(planning_run_id, payload) for payload in rows_by_sheet["Machine_Master"]]
    vendors = [_to_vendor(planning_run_id, payload) for payload in rows_by_sheet["Vendor_Master"]]

    try:
        db.add_all(valves)
        db.flush()
        db.add_all(component_statuses)
        db.add_all(routing_operations)
        db.add_all(machines)
        db.add_all(vendors)
        upload_batch.status = "PROMOTED"
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise PromotionError(
            "PROMOTION_INTEGRITY_ERROR",
            "Canonical promotion violated database constraints. Re-run validation or inspect staged rows.",
        ) from exc

    return PromotionResult(
        upload_batch_id=upload_batch_id,
        planning_run_id=planning_run_id,
        valves=len(valves),
        component_statuses=len(component_statuses),
        routing_operations=len(routing_operations),
        machines=len(machines),
        vendors=len(vendors),
    )


def _load_staging_payloads(upload_batch_id: str, db: Session) -> dict[str, list[dict[str, Any]]]:
    rows = list(
        db.scalars(
            select(ImportStagingRow)
            .where(ImportStagingRow.upload_batch_id == upload_batch_id)
            .order_by(ImportStagingRow.sheet_name, ImportStagingRow.row_number)
        )
    )

    rows_by_sheet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_sheet[row.sheet_name].append(json.loads(row.normalized_payload_json))
    return rows_by_sheet


def _to_valve(planning_run_id: str, payload: dict[str, Any]) -> Valve:
    return Valve(
        id=new_uuid(),
        planning_run_id=planning_run_id,
        valve_id=_required_text(payload, "valve_id"),
        order_id=_required_text(payload, "order_id"),
        customer=_required_text(payload, "customer"),
        valve_type=_optional_text(payload, "valve_type"),
        dispatch_date=_required_text(payload, "dispatch_date"),
        assembly_date=_required_text(payload, "assembly_date"),
        value_cr=_required_number(payload, "value_cr"),
        priority=_optional_text(payload, "priority"),
        status=_optional_text(payload, "status"),
        remarks=_optional_text(payload, "remarks"),
    )


def _to_component_status(planning_run_id: str, payload: dict[str, Any]) -> ComponentStatus:
    fabrication_required = _required_bool(payload, "fabrication_required")
    fabrication_complete = _required_bool(payload, "fabrication_complete")
    return ComponentStatus(
        id=new_uuid(),
        planning_run_id=planning_run_id,
        valve_id=_required_text(payload, "valve_id"),
        component_line_no=_required_int(payload, "component_line_no"),
        component=_required_text(payload, "component"),
        qty=_required_number(payload, "qty"),
        fabrication_required=fabrication_required,
        fabrication_complete=fabrication_complete,
        expected_ready_date=_required_text(payload, "expected_ready_date"),
        critical=_required_bool(payload, "critical"),
        expected_from_fabrication=_optional_text(payload, "expected_from_fabrication"),
        priority_eligible=_optional_bool(payload, "priority_eligible"),
        ready_date_type=_ready_date_type(payload, fabrication_required, fabrication_complete),
        current_location=_optional_text(payload, "current_location"),
        comments=_optional_text(payload, "comments"),
    )


def _to_routing_operation(planning_run_id: str, payload: dict[str, Any]) -> RoutingOperation:
    return RoutingOperation(
        id=new_uuid(),
        planning_run_id=planning_run_id,
        component=_required_text(payload, "component"),
        operation_no=_required_int(payload, "operation_no"),
        operation_name=_required_text(payload, "operation_name"),
        machine_type=_required_text(payload, "machine_type"),
        alt_machine=_optional_text(payload, "alt_machine"),
        std_setup_hrs=_optional_number(payload, "std_setup_hrs"),
        std_run_hrs=_optional_number(payload, "std_run_hrs"),
        std_total_hrs=_required_number(payload, "std_total_hrs"),
        subcontract_allowed=_required_bool(payload, "subcontract_allowed"),
        vendor_process=_optional_text(payload, "vendor_process"),
        notes=_optional_text(payload, "notes"),
    )


def _to_machine(planning_run_id: str, payload: dict[str, Any]) -> Machine:
    hours_per_day = _required_number(payload, "hours_per_day")
    efficiency_percent = _required_number(payload, "efficiency_percent")
    return Machine(
        id=new_uuid(),
        planning_run_id=planning_run_id,
        machine_id=_required_text(payload, "machine_id"),
        machine_type=_required_text(payload, "machine_type"),
        description=_optional_text(payload, "description"),
        hours_per_day=hours_per_day,
        efficiency_percent=efficiency_percent,
        effective_hours_day=hours_per_day * efficiency_percent / 100,
        shift_pattern=_optional_text(payload, "shift_pattern"),
        buffer_days=_required_number(payload, "buffer_days"),
        capability_notes=_optional_text(payload, "capability_notes"),
        active=_required_bool(payload, "active"),
    )


def _to_vendor(planning_run_id: str, payload: dict[str, Any]) -> Vendor:
    turnaround_days = _required_number(payload, "turnaround_days")
    transport_days_total = _required_number(payload, "transport_days_total")
    return Vendor(
        id=new_uuid(),
        planning_run_id=planning_run_id,
        vendor_id=_required_text(payload, "vendor_id"),
        vendor_name=_required_text(payload, "vendor_name"),
        primary_process=_required_text(payload, "primary_process"),
        turnaround_days=turnaround_days,
        transport_days_total=transport_days_total,
        effective_lead_days=turnaround_days + transport_days_total,
        capacity_rating=_optional_text(payload, "capacity_rating"),
        reliability=_optional_text(payload, "reliability"),
        approved=_required_bool(payload, "approved"),
        comments=_optional_text(payload, "comments"),
    )


def _ready_date_type(payload: dict[str, Any], fabrication_required: int, fabrication_complete: int) -> str:
    supplied = _optional_text(payload, "ready_date_type")
    if supplied:
        return supplied.upper()
    if fabrication_complete == 1 or fabrication_required == 0:
        return "CONFIRMED"
    return "EXPECTED"


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = _optional_text(payload, field_name)
    if value is None:
        raise PromotionError("PROMOTION_DATA_ERROR", f"{field_name} is required for canonical promotion.")
    return value


def _optional_text(payload: dict[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _required_number(payload: dict[str, Any], field_name: str) -> float:
    value = _optional_number(payload, field_name)
    if value is None:
        raise PromotionError("PROMOTION_DATA_ERROR", f"{field_name} must be numeric for canonical promotion.")
    return value


def _optional_number(payload: dict[str, Any], field_name: str) -> float | None:
    value = payload.get(field_name)
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _required_int(payload: dict[str, Any], field_name: str) -> int:
    value = _optional_number(payload, field_name)
    if value is None or value % 1 != 0:
        raise PromotionError("PROMOTION_DATA_ERROR", f"{field_name} must be an integer for canonical promotion.")
    return int(value)


def _required_bool(payload: dict[str, Any], field_name: str) -> int:
    value = _optional_bool(payload, field_name)
    if value is None:
        raise PromotionError("PROMOTION_DATA_ERROR", f"{field_name} must be boolean for canonical promotion.")
    return value


def _optional_bool(payload: dict[str, Any], field_name: str) -> int | None:
    value = payload.get(field_name)
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int) and value in (0, 1):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"y", "yes", "true", "1"}:
        return 1
    if normalized in {"n", "no", "false", "0"}:
        return 0
    return None
