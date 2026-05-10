from pydantic import BaseModel


class PlanningRunDashboardSummaryResponse(BaseModel):
    planning_run_id: str
    active_valves: int
    active_value_cr: float
    planned_throughput_value_cr: float
    throughput_gap_cr: float
    overloaded_machines: int
    underutilized_machines: int
    flow_blockers: int
    assembly_risk_valves: int
    subcontract_recommendations: int
    batch_risks: int


class IncomingLoadItemResponse(BaseModel):
    valve_id: str
    customer: str
    valve_type: str | None
    component_line_no: int
    component: str
    qty: float
    availability_date: str
    date_confidence: str
    current_ready_flag: bool
    machine_types: list[str]
    priority_score: float
    sort_sequence: int
    same_day_arrival_load_days: float | None
    batch_risk_flag: bool


class IncomingLoadListResponse(BaseModel):
    items: list[IncomingLoadItemResponse]
    total: int
    page: int
    page_size: int


class MachineLoadSummaryResponse(BaseModel):
    machine_type: str
    total_operation_hours: float
    capacity_hours_per_day: float
    load_days: float
    buffer_days: float
    overload_flag: bool
    overload_days: float
    spare_capacity_days: float
    underutilized_flag: bool
    batch_risk_flag: bool
    status: str
    queue_approximation_warning: str


class MachineLoadListResponse(BaseModel):
    items: list[MachineLoadSummaryResponse]
    total: int
    page: int
    page_size: int


class QueueOperationResponse(BaseModel):
    id: str
    sort_sequence: int
    priority_score: float
    valve_id: str
    customer: str
    component_line_no: int
    component: str
    operation_no: int
    operation_name: str
    availability_date: str
    date_confidence: str
    operation_hours: float
    internal_wait_days: float | None
    processing_time_days: float | None
    internal_completion_date: str | None
    recommendation_status: str | None
    extreme_delay_flag: bool | None


class QueueOperationListResponse(BaseModel):
    machine_type: str
    queue_approximation_warning: str | None
    items: list[QueueOperationResponse]
    total: int
    page: int
    page_size: int


class ValveReadinessItemResponse(BaseModel):
    valve_id: str
    customer: str
    assembly_date: str
    dispatch_date: str
    value_cr: float
    total_components: int
    ready_components: int
    required_components: int
    ready_required_count: int
    pending_required_count: int
    full_kit_flag: bool
    near_ready_flag: bool
    valve_expected_completion_date: str | None
    otd_delay_days: float
    otd_risk_flag: bool
    readiness_status: str
    risk_reason: str | None
    valve_flow_gap_days: float | None
    valve_flow_imbalance_flag: bool


class ValveReadinessListResponse(BaseModel):
    items: list[ValveReadinessItemResponse]
    total: int
    page: int
    page_size: int


class ComponentStatusItemResponse(BaseModel):
    valve_id: str
    customer: str
    component_line_no: int
    component: str
    current_location: str | None
    fabrication_complete: bool
    critical: bool
    availability_date: str
    date_confidence: str
    next_operation_name: str | None
    next_machine_type: str | None
    internal_wait_days: float | None
    status: str
    blocker_types: list[str]
    blocker_summary: str | None


class ComponentStatusListResponse(BaseModel):
    valve_id: str
    items: list[ComponentStatusItemResponse]
    total: int
    page: int
    page_size: int


class AssemblyRiskItemResponse(BaseModel):
    valve_id: str
    customer: str
    assembly_date: str
    expected_completion_date: str | None
    assembly_delay_days: float
    reason: str | None
    suggested_action: str
    value_cr: float


class AssemblyRiskListResponse(BaseModel):
    items: list[AssemblyRiskItemResponse]
    total: int
    page: int
    page_size: int


class RecommendationItemResponse(BaseModel):
    id: str
    planned_operation_id: str | None
    valve_id: str | None
    customer: str | None
    component_line_no: int | None
    component: str | None
    operation_name: str | None
    machine_type: str | None
    recommendation_type: str
    recommendation_status: str | None
    suggested_machine_type: str | None
    suggested_vendor_id: str | None
    suggested_vendor_name: str | None
    internal_wait_days: float | None
    processing_time_days: float | None
    internal_completion_days: float | None
    vendor_total_days: float | None
    vendor_gain_days: float | None
    subcontract_batch_candidate_count: int | None
    batch_subcontract_opportunity_flag: bool
    reason_codes: list[str]
    explanation: str
    status: str


class RecommendationListResponse(BaseModel):
    items: list[RecommendationItemResponse]
    total: int
    page: int
    page_size: int


class FlowBlockerItemResponse(BaseModel):
    id: str
    planned_operation_id: str | None
    valve_id: str | None
    customer: str | None
    component_line_no: int | None
    component: str | None
    operation_name: str | None
    blocker_type: str
    cause: str
    recommended_action: str
    severity: str
    created_at: str


class FlowBlockerListResponse(BaseModel):
    items: list[FlowBlockerItemResponse]
    total: int
    page: int
    page_size: int


class VendorLoadItemResponse(BaseModel):
    vendor_id: str
    vendor_name: str
    primary_process: str
    vendor_recommended_jobs: int
    max_recommended_jobs_per_horizon: int
    selected_vendor_overloaded_flag: bool
    status: str
    capacity_rating: str | None
    reliability: str | None
    comments: str | None
    limitation_warning: str


class VendorLoadListResponse(BaseModel):
    items: list[VendorLoadItemResponse]
    total: int
    page: int
    page_size: int


class ThroughputSummaryResponse(BaseModel):
    planning_run_id: str
    target_throughput_value_cr: float
    planned_throughput_value_cr: float
    throughput_gap_cr: float
    throughput_risk_flag: bool
