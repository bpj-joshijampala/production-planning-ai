from datetime import date
from typing import Literal

from pydantic import BaseModel


class PlanningRunCreateRequest(BaseModel):
    upload_batch_id: str
    planning_start_date: date | None = None
    planning_horizon_days: Literal[7, 14] = 7


class CanonicalCountsResponse(BaseModel):
    valves: int
    component_statuses: int
    routing_operations: int
    machines: int
    vendors: int


class PlanningRunResponse(BaseModel):
    id: str
    upload_batch_id: str
    planning_start_date: str
    planning_horizon_days: int
    status: str
    created_by_user_id: str
    created_at: str
    calculated_at: str | None
    error_message: str | None
    snapshot_id: str
    canonical_counts: CanonicalCountsResponse
