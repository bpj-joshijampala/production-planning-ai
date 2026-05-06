from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import WRITE_ROLES, require_current_user_roles
from app.db.session import get_db
from app.models.user import User
from app.schemas.planner_override import (
    PlannerOverrideCreateRequest,
    PlannerOverrideListResponse,
    PlannerOverrideResponse,
)
from app.services.planner_overrides import create_planner_override, list_planner_overrides

router = APIRouter(tags=["planner-overrides"])


@router.post("/planner-overrides", response_model=PlannerOverrideResponse, status_code=status.HTTP_201_CREATED)
def create_planner_override_endpoint(
    request: PlannerOverrideCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user_roles(*WRITE_ROLES)),
) -> PlannerOverrideResponse:
    return create_planner_override(request=request, db=db, user_id=current_user.id)


@router.get("/planning-runs/{planning_run_id}/planner-overrides", response_model=PlannerOverrideListResponse)
def list_planner_overrides_endpoint(
    planning_run_id: str,
    db: Session = Depends(get_db),
) -> PlannerOverrideListResponse:
    return list_planner_overrides(planning_run_id=planning_run_id, db=db)
