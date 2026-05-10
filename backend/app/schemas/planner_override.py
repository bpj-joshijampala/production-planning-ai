from typing import Literal

from pydantic import BaseModel


class PlannerOverrideCreateRequest(BaseModel):
    planning_run_id: str
    entity_type: Literal["RECOMMENDATION", "OPERATION", "VALVE", "MACHINE", "VENDOR"]
    entity_id: str
    original_recommendation: str | None = None
    override_decision: str
    reason: str
    remarks: str | None = None


class PlannerOverrideResponse(BaseModel):
    id: str
    planning_run_id: str
    recommendation_id: str | None
    entity_type: str
    entity_id: str
    original_recommendation: str | None
    override_decision: str
    reason: str
    remarks: str | None
    stale_flag: bool
    stale_reason: str | None = None
    user_id: str
    user_display_name: str
    created_at: str


class PlannerOverrideListResponse(BaseModel):
    planning_run_id: str
    overrides: list[PlannerOverrideResponse]
    stale_override_count: int = 0
    current_override_count: int = 0
    replanning_policy: str = (
        "Override-driven replanning is deferred in V1. Planner decisions remain audit records and are not "
        "replayed during recalculation."
    )
