from hashlib import sha256
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.models.canonical import ComponentStatus, Machine, RoutingOperation, Valve, Vendor
from app.models.planning_run import PlanningRun, PlanningSnapshot
from app.models.upload import ImportValidationIssue, UploadBatch
from app.schemas.planning_run import CanonicalCountsResponse, PlanningRunCreateRequest, PlanningRunResponse
from app.services.canonical_promotion import PromotionError, PromotionResult, promote_upload_to_canonical

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


def create_planning_run(request: PlanningRunCreateRequest, db: Session) -> PlanningRunResponse:
    upload_batch = _load_upload_for_planning(request.upload_batch_id, db)
    _ensure_upload_can_create_planning_run(upload_batch, db)

    created_at = utc_now_iso()
    planning_run = PlanningRun(
        id=new_uuid(),
        upload_batch_id=upload_batch.id,
        planning_start_date=request.planning_start_date.isoformat(),
        planning_horizon_days=request.planning_horizon_days,
        status="CREATED",
        created_by_user_id=DEV_USER_ID,
        created_at=created_at,
    )

    try:
        db.add(planning_run)
        db.flush()
        promotion_result = promote_upload_to_canonical(
            upload_batch_id=upload_batch.id,
            planning_run_id=planning_run.id,
            db=db,
            commit=False,
        )
        snapshot = _create_snapshot(planning_run, db, created_at)
        db.add(snapshot)
        db.commit()
        db.refresh(planning_run)
        db.refresh(snapshot)
    except PromotionError as exc:
        db.rollback()
        _raise_promotion_http_error(exc)
    except Exception:
        db.rollback()
        raise

    return _to_response(planning_run, snapshot, promotion_result)


def _load_upload_for_planning(upload_batch_id: str, db: Session) -> UploadBatch:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_NOT_FOUND", "message": f"Upload {upload_batch_id} was not found."},
        )
    return upload_batch


def _ensure_upload_can_create_planning_run(upload_batch: UploadBatch, db: Session) -> None:
    blocking_issue_count = db.scalar(
        select(func.count())
        .select_from(ImportValidationIssue)
        .where(ImportValidationIssue.upload_batch_id == upload_batch.id)
        .where(ImportValidationIssue.severity == "BLOCKING")
    )
    if upload_batch.validation_error_count > 0 or blocking_issue_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "VALIDATION_BLOCKED",
                "message": "Upload has blocking validation issues and cannot create a PlanningRun.",
            },
        )

    if upload_batch.status not in {"VALIDATED", "PROMOTED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UPLOAD_NOT_VALIDATED",
                "message": "Upload must be validated before creating a PlanningRun.",
            },
        )


def _create_snapshot(planning_run: PlanningRun, db: Session, created_at: str) -> PlanningSnapshot:
    payload = _snapshot_payload(planning_run, db)
    return PlanningSnapshot(
        id=new_uuid(),
        planning_run_id=planning_run.id,
        snapshot_json=json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        created_at=created_at,
    )


def _snapshot_payload(planning_run: PlanningRun, db: Session) -> dict[str, Any]:
    valves = [_valve_snapshot(row) for row in _canonical_rows(db, Valve, planning_run.id, Valve.valve_id)]
    component_statuses = [
        _component_snapshot(row)
        for row in _canonical_rows(
            db,
            ComponentStatus,
            planning_run.id,
            ComponentStatus.valve_id,
            ComponentStatus.component_line_no,
        )
    ]
    routing_operations = [
        _routing_snapshot(row)
        for row in _canonical_rows(
            db,
            RoutingOperation,
            planning_run.id,
            RoutingOperation.component,
            RoutingOperation.operation_no,
        )
    ]
    machines = [_machine_snapshot(row) for row in _canonical_rows(db, Machine, planning_run.id, Machine.machine_id)]
    vendors = [_vendor_snapshot(row) for row in _canonical_rows(db, Vendor, planning_run.id, Vendor.vendor_id)]

    canonical = {
        "valves": valves,
        "component_statuses": component_statuses,
        "routing_operations": routing_operations,
        "machines": machines,
        "vendors": vendors,
    }

    return {
        "schema_version": 1,
        "planning_run": {
            "id": planning_run.id,
            "upload_batch_id": planning_run.upload_batch_id,
            "planning_start_date": planning_run.planning_start_date,
            "planning_horizon_days": planning_run.planning_horizon_days,
            "status": planning_run.status,
            "created_by_user_id": planning_run.created_by_user_id,
            "created_at": planning_run.created_at,
        },
        "row_counts": {key: len(rows) for key, rows in canonical.items()},
        "canonical_hash": _canonical_hash(canonical),
        "canonical": canonical,
    }


def _canonical_rows(db: Session, model: type[Any], planning_run_id: str, *order_by: Any) -> list[Any]:
    return list(
        db.scalars(
            select(model)
            .where(model.planning_run_id == planning_run_id)
            .order_by(*order_by)
        )
    )


def _canonical_hash(canonical: dict[str, list[dict[str, Any]]]) -> str:
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical_json.encode("utf-8")).hexdigest()


def _valve_snapshot(row: Valve) -> dict[str, Any]:
    return {
        "valve_id": row.valve_id,
        "order_id": row.order_id,
        "customer": row.customer,
        "valve_type": row.valve_type,
        "dispatch_date": row.dispatch_date,
        "assembly_date": row.assembly_date,
        "value_cr": row.value_cr,
        "priority": row.priority,
        "status": row.status,
        "remarks": row.remarks,
    }


def _component_snapshot(row: ComponentStatus) -> dict[str, Any]:
    return {
        "valve_id": row.valve_id,
        "component_line_no": row.component_line_no,
        "component": row.component,
        "qty": row.qty,
        "fabrication_required": row.fabrication_required,
        "fabrication_complete": row.fabrication_complete,
        "expected_ready_date": row.expected_ready_date,
        "critical": row.critical,
        "expected_from_fabrication": row.expected_from_fabrication,
        "priority_eligible": row.priority_eligible,
        "ready_date_type": row.ready_date_type,
        "current_location": row.current_location,
        "comments": row.comments,
    }


def _routing_snapshot(row: RoutingOperation) -> dict[str, Any]:
    return {
        "component": row.component,
        "operation_no": row.operation_no,
        "operation_name": row.operation_name,
        "machine_type": row.machine_type,
        "alt_machine": row.alt_machine,
        "std_setup_hrs": row.std_setup_hrs,
        "std_run_hrs": row.std_run_hrs,
        "std_total_hrs": row.std_total_hrs,
        "subcontract_allowed": row.subcontract_allowed,
        "vendor_process": row.vendor_process,
        "notes": row.notes,
    }


def _machine_snapshot(row: Machine) -> dict[str, Any]:
    return {
        "machine_id": row.machine_id,
        "machine_type": row.machine_type,
        "description": row.description,
        "hours_per_day": row.hours_per_day,
        "efficiency_percent": row.efficiency_percent,
        "effective_hours_day": row.effective_hours_day,
        "shift_pattern": row.shift_pattern,
        "buffer_days": row.buffer_days,
        "capability_notes": row.capability_notes,
        "active": row.active,
    }


def _vendor_snapshot(row: Vendor) -> dict[str, Any]:
    return {
        "vendor_id": row.vendor_id,
        "vendor_name": row.vendor_name,
        "primary_process": row.primary_process,
        "turnaround_days": row.turnaround_days,
        "transport_days_total": row.transport_days_total,
        "effective_lead_days": row.effective_lead_days,
        "capacity_rating": row.capacity_rating,
        "reliability": row.reliability,
        "approved": row.approved,
        "comments": row.comments,
    }


def _to_response(
    planning_run: PlanningRun,
    snapshot: PlanningSnapshot,
    promotion_result: PromotionResult,
) -> PlanningRunResponse:
    return PlanningRunResponse(
        id=planning_run.id,
        upload_batch_id=planning_run.upload_batch_id,
        planning_start_date=planning_run.planning_start_date,
        planning_horizon_days=planning_run.planning_horizon_days,
        status=planning_run.status,
        created_by_user_id=planning_run.created_by_user_id,
        created_at=planning_run.created_at,
        calculated_at=planning_run.calculated_at,
        error_message=planning_run.error_message,
        snapshot_id=snapshot.id,
        canonical_counts=CanonicalCountsResponse(
            valves=promotion_result.valves,
            component_statuses=promotion_result.component_statuses,
            routing_operations=promotion_result.routing_operations,
            machines=promotion_result.machines,
            vendors=promotion_result.vendors,
        ),
    )


def _raise_promotion_http_error(exc: PromotionError) -> None:
    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code in {"UPLOAD_NOT_FOUND", "PLANNING_RUN_NOT_FOUND"}:
        status_code = status.HTTP_404_NOT_FOUND

    raise HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    ) from exc
