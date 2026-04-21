from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.planning_run import PlanningRunCreateRequest, PlanningRunResponse
from app.services.planning_runs import create_planning_run

router = APIRouter(prefix="/planning-runs", tags=["planning-runs"])


@router.post("", response_model=PlanningRunResponse, status_code=status.HTTP_201_CREATED)
def create_planning_run_endpoint(
    request: PlanningRunCreateRequest,
    db: Session = Depends(get_db),
) -> PlanningRunResponse:
    return create_planning_run(request=request, db=db)
