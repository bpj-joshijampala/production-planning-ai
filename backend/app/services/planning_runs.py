from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.models.canonical import Valve, Vendor
from app.models.output import MachineLoadSummary, PlannerOverride, PlannedOperation, Recommendation
from app.models.planning_run import PlanningRun, PlanningSnapshot
from app.models.upload import ImportValidationIssue, UploadBatch
from app.planning.input_loader import PlanningSettingsOverride, build_planning_settings
from app.schemas.planning_run import CanonicalCountsResponse, PlanningRunCreateRequest, PlanningRunResponse
from app.services.canonical_promotion import PromotionError, PromotionResult, promote_upload_to_canonical
from app.services.incoming_load import calculate_and_persist_incoming_load
from app.services.machine_load import calculate_and_persist_machine_load
from app.services.planning_run_metadata import upsert_planning_run_metadata
from app.services.recommendations import calculate_and_persist_placeholder_recommendations
from app.services.throughput import calculate_and_persist_throughput_summary

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


def create_planning_run(request: PlanningRunCreateRequest, db: Session) -> PlanningRunResponse:
    upload_batch = _load_upload_for_planning(request.upload_batch_id, db)
    _ensure_upload_can_create_planning_run(upload_batch, db)

    created_at = utc_now_iso()
    planning_run = PlanningRun(
        id=new_uuid(),
        upload_batch_id=upload_batch.id,
        planning_start_date=_resolve_planning_start_date(request, upload_batch).isoformat(),
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
        snapshot = upsert_planning_run_metadata(planning_run.id, db, created_at=created_at)
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


def recalculate_planning_run(
    planning_run_id: str,
    db: Session,
    *,
    settings_override: PlanningSettingsOverride | None = None,
) -> PlanningRun:
    planning_run = _load_planning_run(planning_run_id, db)
    previous_calculated_at = planning_run.calculated_at

    try:
        planning_run.status = "CALCULATING"
        planning_run.error_message = None
        db.flush()
        effective_settings = build_planning_settings(
            planning_start_date=(
                planning_run.planning_start_date
                if settings_override is None or settings_override.planning_start_date is None
                else settings_override.planning_start_date
            ),
            planning_horizon_days=(
                planning_run.planning_horizon_days
                if settings_override is None or settings_override.planning_horizon_days is None
                else settings_override.planning_horizon_days
            ),
        )

        # Recalculation only refreshes calculated-output tables owned by the engine.
        # Planner overrides are append-only and intentionally preserved across recalculation.
        calculate_and_persist_incoming_load(
            planning_run_id=planning_run_id,
            db=db,
            settings_override=settings_override,
            commit=False,
        )
        calculate_and_persist_machine_load(
            planning_run_id=planning_run_id,
            db=db,
            settings_override=settings_override,
            commit=False,
        )
        calculate_and_persist_throughput_summary(
            planning_run_id=planning_run_id,
            db=db,
            settings_override=settings_override,
            commit=False,
        )
        calculate_and_persist_placeholder_recommendations(
            planning_run_id=planning_run_id,
            db=db,
            commit=False,
        )
        _mark_planner_overrides_stale_for_missing_targets(planning_run_id=planning_run_id, db=db)

        upload_batch = _load_upload_for_planning(planning_run.upload_batch_id, db)
        upload_batch.status = "CALCULATED"
        planning_run.status = "CALCULATED"
        planning_run.calculated_at = utc_now_iso()
        planning_run.error_message = None
        upsert_planning_run_metadata(
            planning_run.id,
            db,
            planning_settings=effective_settings if settings_override is not None else None,
            created_at=planning_run.calculated_at,
        )
        db.commit()
        db.refresh(planning_run)
        return planning_run
    except Exception as exc:
        db.rollback()
        _mark_planning_run_failed(
            planning_run_id=planning_run_id,
            error_message=str(exc),
            calculated_at=previous_calculated_at,
            db=db,
        )
        raise


def _load_upload_for_planning(upload_batch_id: str, db: Session) -> UploadBatch:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "UPLOAD_NOT_FOUND", "message": f"Upload {upload_batch_id} was not found."},
        )
    return upload_batch


def _load_planning_run(planning_run_id: str, db: Session) -> PlanningRun:
    planning_run = db.get(PlanningRun, planning_run_id)
    if planning_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLANNING_RUN_NOT_FOUND", "message": f"PlanningRun {planning_run_id} was not found."},
        )
    return planning_run


def _mark_planning_run_failed(
    *,
    planning_run_id: str,
    error_message: str,
    calculated_at: str | None,
    db: Session,
) -> None:
    try:
        planning_run = db.get(PlanningRun, planning_run_id)
        if planning_run is None:
            return
        planning_run.status = "FAILED"
        planning_run.error_message = error_message
        planning_run.calculated_at = calculated_at
        db.commit()
    except Exception:
        db.rollback()


def _mark_planner_overrides_stale_for_missing_targets(*, planning_run_id: str, db: Session) -> None:
    overrides = list(
        db.scalars(
            select(PlannerOverride)
            .where(PlannerOverride.planning_run_id == planning_run_id)
            .order_by(PlannerOverride.created_at.asc(), PlannerOverride.id.asc())
        )
    )
    if not overrides:
        return

    planned_operation_ids = {
        row.id for row in db.scalars(select(PlannedOperation).where(PlannedOperation.planning_run_id == planning_run_id))
    }
    valve_ids = {
        row.valve_id for row in db.scalars(select(Valve).where(Valve.planning_run_id == planning_run_id))
    }
    machine_types = {
        row.machine_type
        for row in db.scalars(select(MachineLoadSummary).where(MachineLoadSummary.planning_run_id == planning_run_id))
    }
    vendor_ids = {
        row.vendor_id for row in db.scalars(select(Vendor).where(Vendor.planning_run_id == planning_run_id))
    }
    known_recommendation_ids = {
        row.id for row in db.scalars(select(Recommendation).where(Recommendation.planning_run_id == planning_run_id))
    }

    for override in overrides:
        override.stale_flag = 1 if _planner_override_target_missing(
            override=override,
            planned_operation_ids=planned_operation_ids,
            valve_ids=valve_ids,
            machine_types=machine_types,
            vendor_ids=vendor_ids,
            recommendation_ids=known_recommendation_ids,
        ) else 0


def _planner_override_target_missing(
    *,
    override: PlannerOverride,
    planned_operation_ids: set[str],
    valve_ids: set[str],
    machine_types: set[str],
    vendor_ids: set[str],
    recommendation_ids: set[str],
) -> bool:
    if override.entity_type == "OPERATION":
        return override.entity_id not in planned_operation_ids
    if override.entity_type == "VALVE":
        return override.entity_id not in valve_ids
    if override.entity_type == "MACHINE":
        return override.entity_id not in machine_types
    if override.entity_type == "VENDOR":
        return override.entity_id not in vendor_ids
    if override.entity_type == "RECOMMENDATION":
        if override.recommendation_id is not None:
            return override.recommendation_id not in recommendation_ids
        return override.entity_id not in recommendation_ids
    return True


def _resolve_planning_start_date(request: PlanningRunCreateRequest, upload_batch: UploadBatch) -> date:
    if request.planning_start_date is not None:
        return request.planning_start_date
    try:
        return date.fromisoformat(upload_batch.uploaded_at[:10])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INVALID_UPLOAD_TIMESTAMP",
                "message": f"Upload {upload_batch.id} does not have a valid upload date.",
            },
        ) from exc


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
