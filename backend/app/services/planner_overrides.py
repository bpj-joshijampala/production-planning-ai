from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import DEFAULT_DEV_USER_ID, WRITE_ROLES, load_acting_user_for_roles
from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.models.canonical import Valve, Vendor
from app.models.output import MachineLoadSummary, PlannerOverride, PlannedOperation, Recommendation
from app.models.planning_run import PlanningRun
from app.models.user import User
from app.schemas.planner_override import (
    PlannerOverrideCreateRequest,
    PlannerOverrideListResponse,
    PlannerOverrideResponse,
)

ALLOWED_OVERRIDE_DECISIONS = {
    "ACCEPT",
    "REJECT",
    "FORCE_IN_HOUSE",
    "FORCE_VENDOR",
    "CHANGE_MACHINE_ASSIGNMENT",
    "OVERRIDE_PRIORITY",
    "ADD_REMARKS",
    "OVERRIDE",
}

def create_planner_override(
    request: PlannerOverrideCreateRequest,
    db: Session,
    *,
    user_id: str = DEFAULT_DEV_USER_ID,
) -> PlannerOverrideResponse:
    acting_user = load_acting_user_for_roles(user_id=user_id, db=db, allowed_roles=WRITE_ROLES)
    planning_run = _load_planning_run(request.planning_run_id, db)
    _require_non_blank(request.reason, code="OVERRIDE_REQUIRES_REASON", message="Reason is required.")
    entity_id = _required_trimmed_value(
        request.entity_id,
        code="OVERRIDE_REQUIRES_ENTITY_ID",
        message="Entity ID is required.",
    )
    override_decision = _normalized_override_decision(
        request.override_decision,
        code="OVERRIDE_REQUIRES_DECISION",
        message="Override decision is required.",
    )
    requested_original_recommendation = _optional_trimmed_value(request.original_recommendation)
    reason = request.reason.strip()
    remarks = _optional_trimmed_value(request.remarks)

    recommendation_id: str | None = None
    original_recommendation = requested_original_recommendation
    if request.entity_type == "RECOMMENDATION":
        recommendation = _load_recommendation(planning_run.id, entity_id, db)
        recommendation_id = recommendation.id
        original_recommendation = recommendation.recommendation_type
        recommendation.status = _recommendation_status_for_override_decision(override_decision)
    else:
        _ensure_override_target_exists(
            planning_run_id=planning_run.id,
            entity_type=request.entity_type,
            entity_id=entity_id,
            db=db,
        )

    override = PlannerOverride(
        id=new_uuid(),
        planning_run_id=planning_run.id,
        recommendation_id=recommendation_id,
        entity_type=request.entity_type,
        entity_id=entity_id,
        original_recommendation=original_recommendation,
        override_decision=override_decision,
        reason=reason,
        remarks=remarks,
        stale_flag=0,
        user_id=acting_user.id,
        created_at=utc_now_iso(),
    )

    try:
        db.add(override)
        db.commit()
        db.refresh(override)
    except Exception:
        db.rollback()
        raise

    return _to_response(override=override, user_display_name=acting_user.display_name)


def list_planner_overrides(planning_run_id: str, db: Session) -> PlannerOverrideListResponse:
    _load_planning_run(planning_run_id, db)
    overrides = list(
        db.scalars(
            select(PlannerOverride)
            .where(PlannerOverride.planning_run_id == planning_run_id)
            .order_by(PlannerOverride.created_at.desc(), PlannerOverride.id.desc())
        )
    )
    user_display_name_by_id = {
        row.id: row.display_name
        for row in db.scalars(select(User).where(User.id.in_({row.user_id for row in overrides})))
    }
    stale_override_count = sum(1 for row in overrides if row.stale_flag == 1)
    return PlannerOverrideListResponse(
        planning_run_id=planning_run_id,
        overrides=[
            _to_response(
                override=row,
                user_display_name=user_display_name_by_id.get(row.user_id, row.user_id),
            )
            for row in overrides
        ],
        stale_override_count=stale_override_count,
        current_override_count=len(overrides) - stale_override_count,
    )


def _load_planning_run(planning_run_id: str, db: Session) -> PlanningRun:
    planning_run = db.get(PlanningRun, planning_run_id)
    if planning_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PLANNING_RUN_NOT_FOUND",
                "message": f"PlanningRun {planning_run_id} was not found.",
            },
        )
    return planning_run


def _load_recommendation(planning_run_id: str, recommendation_id: str, db: Session) -> Recommendation:
    recommendation = db.scalar(
        select(Recommendation)
        .where(Recommendation.planning_run_id == planning_run_id)
        .where(Recommendation.id == recommendation_id)
    )
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RECOMMENDATION_NOT_FOUND",
                "message": f"Recommendation {recommendation_id} was not found in PlanningRun {planning_run_id}.",
            },
        )
    return recommendation


def _ensure_override_target_exists(
    *,
    planning_run_id: str,
    entity_type: str,
    entity_id: str,
    db: Session,
) -> None:
    if entity_type == "OPERATION":
        target = db.scalar(
            select(PlannedOperation)
            .where(PlannedOperation.planning_run_id == planning_run_id)
            .where(PlannedOperation.id == entity_id)
        )
        if target is None:
            _raise_target_not_found("OPERATION", entity_id, planning_run_id)
        return
    if entity_type == "VALVE":
        target = db.scalar(
            select(Valve)
            .where(Valve.planning_run_id == planning_run_id)
            .where(Valve.valve_id == entity_id)
        )
        if target is None:
            _raise_target_not_found("VALVE", entity_id, planning_run_id)
        return
    if entity_type == "MACHINE":
        target = db.scalar(
            select(MachineLoadSummary)
            .where(MachineLoadSummary.planning_run_id == planning_run_id)
            .where(MachineLoadSummary.machine_type == entity_id)
        )
        if target is None:
            _raise_target_not_found("MACHINE", entity_id, planning_run_id)
        return
    if entity_type == "VENDOR":
        target = db.scalar(
            select(Vendor)
            .where(Vendor.planning_run_id == planning_run_id)
            .where(Vendor.vendor_id == entity_id)
        )
        if target is None:
            _raise_target_not_found("VENDOR", entity_id, planning_run_id)
        return


def _raise_target_not_found(entity_type: str, entity_id: str, planning_run_id: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": f"{entity_type}_NOT_FOUND",
            "message": f"{entity_type.title()} target {entity_id} was not found in PlanningRun {planning_run_id}.",
        },
    )


def _recommendation_status_for_override_decision(override_decision: str) -> str:
    if override_decision in {"ACCEPT", "ACCEPTED"}:
        return "ACCEPTED"
    if override_decision in {"REJECT", "REJECTED"}:
        return "REJECTED"
    return "OVERRIDDEN"


def _normalized_override_decision(value: str, *, code: str, message: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )
    normalized = trimmed.upper()
    if normalized not in ALLOWED_OVERRIDE_DECISIONS:
        allowed_values = ", ".join(sorted(ALLOWED_OVERRIDE_DECISIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_OVERRIDE_DECISION",
                "message": f"Override decision {trimmed} is not supported. Use one of: {allowed_values}.",
            },
        )
    return normalized


def _required_trimmed_value(value: str, *, code: str, message: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )
    return trimmed


def _optional_trimmed_value(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _require_non_blank(value: str, *, code: str, message: str) -> None:
    if not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )


def _to_response(*, override: PlannerOverride, user_display_name: str) -> PlannerOverrideResponse:
    return PlannerOverrideResponse(
        id=override.id,
        planning_run_id=override.planning_run_id,
        recommendation_id=override.recommendation_id,
        entity_type=override.entity_type,
        entity_id=override.entity_id,
        original_recommendation=override.original_recommendation,
        override_decision=override.override_decision,
        reason=override.reason,
        remarks=override.remarks,
        stale_flag=bool(override.stale_flag),
        stale_reason=_stale_reason(override),
        user_id=override.user_id,
        user_display_name=user_display_name,
        created_at=override.created_at,
    )


def _stale_reason(override: PlannerOverride) -> str | None:
    if override.stale_flag != 1:
        return None
    target_label = {
        "RECOMMENDATION": "Recommendation",
        "OPERATION": "Operation",
        "VALVE": "Valve",
        "MACHINE": "Machine",
        "VENDOR": "Vendor",
    }.get(override.entity_type, "Override")
    return (
        f"{target_label} target is stale or orphaned after recalculation. "
        "The decision remains in the action log but is not replayed in V1."
    )
