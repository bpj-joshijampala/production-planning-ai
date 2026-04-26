from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.db.base import Base


class IncomingLoadItem(Base):
    __tablename__ = "incoming_load_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["planning_run_id", "valve_id", "component_line_no"],
            ["component_statuses.planning_run_id", "component_statuses.valve_id", "component_statuses.component_line_no"],
            name="fk_incoming_load_items_run_valve_line",
        ),
        UniqueConstraint(
            "planning_run_id",
            "valve_id",
            "component_line_no",
            name="uq_incoming_load_items_run_valve_line",
        ),
        CheckConstraint("qty > 0", name="ck_incoming_load_items_qty_positive"),
        CheckConstraint(
            "date_confidence in ('CONFIRMED', 'EXPECTED', 'TENTATIVE')",
            name="ck_incoming_load_items_date_confidence",
        ),
        CheckConstraint("current_ready_flag in (0, 1)", name="ck_incoming_load_items_current_ready_flag_bool"),
        CheckConstraint(
            "machine_types_json is null or json_valid(machine_types_json)",
            name="ck_incoming_load_items_machine_types_json",
        ),
        CheckConstraint(
            "machine_types_json is null or json_type(machine_types_json) = 'array'",
            name="ck_incoming_load_items_machine_types_json_array",
        ),
        CheckConstraint("sort_sequence > 0", name="ck_incoming_load_items_sort_sequence_positive"),
        CheckConstraint(
            "same_day_arrival_load_days is null or same_day_arrival_load_days >= 0",
            name="ck_incoming_load_items_same_day_arrival_load_days_nonnegative",
        ),
        CheckConstraint("batch_risk_flag in (0, 1)", name="ck_incoming_load_items_batch_risk_flag_bool"),
        Index("ix_incoming_load_items_run_availability_date", "planning_run_id", "availability_date"),
        Index("ix_incoming_load_items_run_valve", "planning_run_id", "valve_id"),
        Index("ix_incoming_load_items_run_date_confidence", "planning_run_id", "date_confidence"),
        Index("ix_incoming_load_items_run_sort_sequence", "planning_run_id", "sort_sequence"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    valve_id: Mapped[str] = mapped_column(String, nullable=False)
    component_line_no: Mapped[int] = mapped_column(nullable=False)
    component: Mapped[str] = mapped_column(String, nullable=False)
    qty: Mapped[float] = mapped_column(nullable=False)
    availability_date: Mapped[str] = mapped_column(String, nullable=False)
    date_confidence: Mapped[str] = mapped_column(String, nullable=False)
    current_ready_flag: Mapped[int] = mapped_column(nullable=False)
    machine_types_json: Mapped[str | None] = mapped_column(String, nullable=True)
    priority_score: Mapped[float] = mapped_column(nullable=False)
    sort_sequence: Mapped[int] = mapped_column(nullable=False)
    same_day_arrival_load_days: Mapped[float | None] = mapped_column(nullable=True)
    batch_risk_flag: Mapped[int] = mapped_column(nullable=False)


class PlannedOperation(Base):
    __tablename__ = "planned_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["planning_run_id", "valve_id", "component_line_no"],
            ["component_statuses.planning_run_id", "component_statuses.valve_id", "component_statuses.component_line_no"],
            name="fk_planned_operations_run_valve_line",
        ),
        UniqueConstraint(
            "planning_run_id",
            "valve_id",
            "component_line_no",
            "operation_no",
            name="uq_planned_operations_run_valve_line_operation",
        ),
        CheckConstraint("operation_no > 0", name="ck_planned_operations_operation_no_positive"),
        CheckConstraint("qty > 0", name="ck_planned_operations_qty_positive"),
        CheckConstraint("operation_hours > 0", name="ck_planned_operations_operation_hours_positive"),
        CheckConstraint(
            "date_confidence in ('CONFIRMED', 'EXPECTED', 'TENTATIVE')",
            name="ck_planned_operations_date_confidence",
        ),
        CheckConstraint("sort_sequence > 0", name="ck_planned_operations_sort_sequence_positive"),
        CheckConstraint(
            "availability_offset_days >= 0",
            name="ck_planned_operations_availability_offset_days_nonnegative",
        ),
        CheckConstraint(
            "operation_arrival_offset_days is null or operation_arrival_offset_days >= 0",
            name="ck_planned_operations_operation_arrival_offset_days_nonnegative",
        ),
        CheckConstraint(
            "scheduled_start_offset_days is null or scheduled_start_offset_days >= 0",
            name="ck_planned_operations_scheduled_start_offset_days_nonnegative",
        ),
        CheckConstraint(
            "internal_wait_days is null or internal_wait_days >= 0",
            name="ck_planned_operations_internal_wait_days_nonnegative",
        ),
        CheckConstraint(
            "processing_time_days is null or processing_time_days >= 0",
            name="ck_planned_operations_processing_time_days_nonnegative",
        ),
        CheckConstraint(
            "internal_completion_days is null or internal_completion_days >= 0",
            name="ck_planned_operations_internal_completion_days_nonnegative",
        ),
        CheckConstraint(
            "internal_completion_offset_days is null or internal_completion_offset_days >= 0",
            name="ck_planned_operations_internal_completion_offset_days_nonnegative",
        ),
        CheckConstraint(
            "extreme_delay_flag is null or extreme_delay_flag in (0, 1)",
            name="ck_planned_operations_extreme_delay_flag_bool",
        ),
        Index("ix_planned_operations_run_machine_type", "planning_run_id", "machine_type"),
        Index("ix_planned_operations_run_valve", "planning_run_id", "valve_id"),
        Index("ix_planned_operations_run_internal_completion_date", "planning_run_id", "internal_completion_date"),
        Index("ix_planned_operations_run_sort_sequence", "planning_run_id", "sort_sequence"),
        Index("ix_planned_operations_run_extreme_delay_flag", "planning_run_id", "extreme_delay_flag"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    valve_id: Mapped[str] = mapped_column(String, nullable=False)
    component_line_no: Mapped[int] = mapped_column(nullable=False)
    component: Mapped[str] = mapped_column(String, nullable=False)
    operation_no: Mapped[int] = mapped_column(nullable=False)
    operation_name: Mapped[str] = mapped_column(String, nullable=False)
    machine_type: Mapped[str] = mapped_column(String, nullable=False)
    alt_machine: Mapped[str | None] = mapped_column(String, nullable=True)
    qty: Mapped[float] = mapped_column(nullable=False)
    operation_hours: Mapped[float] = mapped_column(nullable=False)
    availability_date: Mapped[str] = mapped_column(String, nullable=False)
    date_confidence: Mapped[str] = mapped_column(String, nullable=False)
    priority_score: Mapped[float] = mapped_column(nullable=False)
    sort_sequence: Mapped[int] = mapped_column(nullable=False)
    availability_offset_days: Mapped[float] = mapped_column(nullable=False)
    operation_arrival_offset_days: Mapped[float | None] = mapped_column(nullable=True)
    operation_arrival_date: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduled_start_offset_days: Mapped[float | None] = mapped_column(nullable=True)
    internal_wait_days: Mapped[float | None] = mapped_column(nullable=True)
    processing_time_days: Mapped[float | None] = mapped_column(nullable=True)
    internal_completion_days: Mapped[float | None] = mapped_column(nullable=True)
    internal_completion_offset_days: Mapped[float | None] = mapped_column(nullable=True)
    internal_completion_date: Mapped[str | None] = mapped_column(String, nullable=True)
    extreme_delay_flag: Mapped[int | None] = mapped_column(nullable=True)
    recommendation_status: Mapped[str | None] = mapped_column(String, nullable=True)


class MachineLoadSummary(Base):
    __tablename__ = "machine_load_summaries"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "machine_type", name="uq_machine_load_summaries_run_machine_type"),
        CheckConstraint(
            "total_operation_hours >= 0",
            name="ck_machine_load_summaries_total_operation_hours_nonnegative",
        ),
        CheckConstraint(
            "capacity_hours_per_day >= 0",
            name="ck_machine_load_summaries_capacity_hours_per_day_nonnegative",
        ),
        CheckConstraint("load_days >= 0", name="ck_machine_load_summaries_load_days_nonnegative"),
        CheckConstraint("buffer_days >= 0", name="ck_machine_load_summaries_buffer_days_nonnegative"),
        CheckConstraint("overload_flag in (0, 1)", name="ck_machine_load_summaries_overload_flag_bool"),
        CheckConstraint("overload_days >= 0", name="ck_machine_load_summaries_overload_days_nonnegative"),
        CheckConstraint(
            "spare_capacity_days >= 0",
            name="ck_machine_load_summaries_spare_capacity_days_nonnegative",
        ),
        CheckConstraint(
            "underutilized_flag in (0, 1)",
            name="ck_machine_load_summaries_underutilized_flag_bool",
        ),
        CheckConstraint("batch_risk_flag in (0, 1)", name="ck_machine_load_summaries_batch_risk_flag_bool"),
        CheckConstraint(
            "status in ('OK', 'OVERLOADED', 'UNDERUTILIZED', 'DATA_INCOMPLETE')",
            name="ck_machine_load_summaries_status",
        ),
        Index("ix_machine_load_summaries_run_machine_type", "planning_run_id", "machine_type"),
        Index("ix_machine_load_summaries_run_status", "planning_run_id", "status"),
        Index("ix_machine_load_summaries_run_overload_flag", "planning_run_id", "overload_flag"),
        Index(
            "ix_machine_load_summaries_run_underutilized_flag",
            "planning_run_id",
            "underutilized_flag",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    machine_type: Mapped[str] = mapped_column(String, nullable=False)
    total_operation_hours: Mapped[float] = mapped_column(nullable=False)
    capacity_hours_per_day: Mapped[float] = mapped_column(nullable=False)
    load_days: Mapped[float] = mapped_column(nullable=False)
    buffer_days: Mapped[float] = mapped_column(nullable=False)
    overload_flag: Mapped[int] = mapped_column(nullable=False)
    overload_days: Mapped[float] = mapped_column(nullable=False)
    spare_capacity_days: Mapped[float] = mapped_column(nullable=False)
    underutilized_flag: Mapped[int] = mapped_column(nullable=False)
    batch_risk_flag: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    queue_approximation_warning: Mapped[str] = mapped_column(String, nullable=False)


class ThroughputSummary(Base):
    __tablename__ = "throughput_summaries"
    __table_args__ = (
        UniqueConstraint("planning_run_id", name="uq_throughput_summaries_run"),
        CheckConstraint(
            "target_throughput_value_cr >= 0",
            name="ck_throughput_summaries_target_throughput_value_cr_nonnegative",
        ),
        CheckConstraint(
            "planned_throughput_value_cr >= 0",
            name="ck_throughput_summaries_planned_throughput_value_cr_nonnegative",
        ),
        CheckConstraint("throughput_gap_cr >= 0", name="ck_throughput_summaries_throughput_gap_cr_nonnegative"),
        CheckConstraint("throughput_risk_flag in (0, 1)", name="ck_throughput_summaries_throughput_risk_flag_bool"),
        Index("ix_throughput_summaries_run_risk_flag", "planning_run_id", "throughput_risk_flag"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    target_throughput_value_cr: Mapped[float] = mapped_column(nullable=False)
    planned_throughput_value_cr: Mapped[float] = mapped_column(nullable=False)
    throughput_gap_cr: Mapped[float] = mapped_column(nullable=False)
    throughput_risk_flag: Mapped[int] = mapped_column(nullable=False)


class VendorLoadSummary(Base):
    __tablename__ = "vendor_load_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["planning_run_id", "vendor_id"],
            ["vendors.planning_run_id", "vendors.vendor_id"],
            name="fk_vendor_load_summaries_run_vendor",
        ),
        UniqueConstraint(
            "planning_run_id",
            "vendor_id",
            "primary_process",
            name="uq_vendor_load_summaries_run_vendor_process",
        ),
        CheckConstraint(
            "vendor_recommended_jobs >= 0",
            name="ck_vendor_load_summaries_vendor_recommended_jobs_nonnegative",
        ),
        CheckConstraint(
            "max_recommended_jobs_per_horizon > 0",
            name="ck_vendor_load_summaries_max_recommended_jobs_positive",
        ),
        CheckConstraint(
            "selected_vendor_overloaded_flag in (0, 1)",
            name="ck_vendor_load_summaries_selected_vendor_overloaded_flag_bool",
        ),
        CheckConstraint(
            "status in ('OK', 'VENDOR_OVERLOADED')",
            name="ck_vendor_load_summaries_status",
        ),
        Index("ix_vendor_load_summaries_run_vendor", "planning_run_id", "vendor_id"),
        Index("ix_vendor_load_summaries_run_status", "planning_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    vendor_id: Mapped[str] = mapped_column(String, nullable=False)
    vendor_name: Mapped[str] = mapped_column(String, nullable=False)
    primary_process: Mapped[str] = mapped_column(String, nullable=False)
    vendor_recommended_jobs: Mapped[int] = mapped_column(nullable=False)
    max_recommended_jobs_per_horizon: Mapped[int] = mapped_column(nullable=False)
    selected_vendor_overloaded_flag: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            (
                "recommendation_type in ("
                "'OK_INTERNAL','MACHINE_OVERLOAD','USE_ALTERNATE','SUBCONTRACT',"
                "'HOLD_FOR_PRIORITY_FLOW','EXTREME_DELAY','BATCH_SUBCONTRACT_OPPORTUNITY',"
                "'BATCH_RISK','FLOW_BLOCKER','NO_FEASIBLE_OPTION','DATA_ERROR'"
                ")"
            ),
            name="ck_recommendations_recommendation_type",
        ),
        CheckConstraint(
            "internal_wait_days is null or internal_wait_days >= 0",
            name="ck_recommendations_internal_wait_days_nonnegative",
        ),
        CheckConstraint(
            "processing_time_days is null or processing_time_days >= 0",
            name="ck_recommendations_processing_time_days_nonnegative",
        ),
        CheckConstraint(
            "internal_completion_days is null or internal_completion_days >= 0",
            name="ck_recommendations_internal_completion_days_nonnegative",
        ),
        CheckConstraint(
            "vendor_total_days is null or vendor_total_days >= 0",
            name="ck_recommendations_vendor_total_days_nonnegative",
        ),
        CheckConstraint(
            "vendor_gain_days is null or vendor_gain_days >= 0",
            name="ck_recommendations_vendor_gain_days_nonnegative",
        ),
        CheckConstraint(
            "subcontract_batch_candidate_count is null or subcontract_batch_candidate_count >= 0",
            name="ck_recommendations_subcontract_batch_candidate_count_nonnegative",
        ),
        CheckConstraint(
            "batch_subcontract_opportunity_flag in (0, 1)",
            name="ck_recommendations_batch_subcontract_opportunity_flag_bool",
        ),
        CheckConstraint(
            "json_valid(reason_codes_json) and json_type(reason_codes_json) = 'array'",
            name="ck_recommendations_reason_codes_json",
        ),
        CheckConstraint(
            "status in ('PENDING', 'ACCEPTED', 'REJECTED', 'OVERRIDDEN')",
            name="ck_recommendations_status",
        ),
        Index("ix_recommendations_run_type", "planning_run_id", "recommendation_type"),
        Index("ix_recommendations_run_status", "planning_run_id", "status"),
        Index("ix_recommendations_run_vendor", "planning_run_id", "suggested_vendor_id"),
        Index("ix_recommendations_planned_operation", "planned_operation_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    planned_operation_id: Mapped[str | None] = mapped_column(ForeignKey("planned_operations.id"), nullable=True)
    recommendation_type: Mapped[str] = mapped_column(String, nullable=False)
    valve_id: Mapped[str | None] = mapped_column(String, nullable=True)
    component_line_no: Mapped[int | None] = mapped_column(nullable=True)
    component: Mapped[str | None] = mapped_column(String, nullable=True)
    operation_name: Mapped[str | None] = mapped_column(String, nullable=True)
    machine_type: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_machine_type: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_vendor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    suggested_vendor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    internal_wait_days: Mapped[float | None] = mapped_column(nullable=True)
    processing_time_days: Mapped[float | None] = mapped_column(nullable=True)
    internal_completion_days: Mapped[float | None] = mapped_column(nullable=True)
    vendor_total_days: Mapped[float | None] = mapped_column(nullable=True)
    vendor_gain_days: Mapped[float | None] = mapped_column(nullable=True)
    subcontract_batch_candidate_count: Mapped[int | None] = mapped_column(nullable=True)
    batch_subcontract_opportunity_flag: Mapped[int] = mapped_column(nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(String, nullable=False)
    explanation: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class PlannerOverride(Base):
    __tablename__ = "planner_overrides"
    __table_args__ = (
        CheckConstraint(
            "entity_type in ('RECOMMENDATION', 'OPERATION', 'VALVE', 'MACHINE', 'VENDOR')",
            name="ck_planner_overrides_entity_type",
        ),
        CheckConstraint("length(trim(entity_id)) > 0", name="ck_planner_overrides_entity_id_not_blank"),
        CheckConstraint("length(trim(override_decision)) > 0", name="ck_planner_overrides_override_decision_not_blank"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_planner_overrides_reason_not_blank"),
        CheckConstraint("stale_flag in (0, 1)", name="ck_planner_overrides_stale_flag_bool"),
        Index("ix_planner_overrides_run", "planning_run_id"),
        Index("ix_planner_overrides_recommendation", "recommendation_id"),
        Index("ix_planner_overrides_user", "user_id"),
        Index("ix_planner_overrides_stale_flag", "stale_flag"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    recommendation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    original_recommendation: Mapped[str | None] = mapped_column(String, nullable=True)
    override_decision: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    remarks: Mapped[str | None] = mapped_column(String, nullable=True)
    stale_flag: Mapped[int] = mapped_column(nullable=False, default=0)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class FlowBlocker(Base):
    __tablename__ = "flow_blockers"
    __table_args__ = (
        CheckConstraint(
            (
                "blocker_type in ("
                "'MISSING_COMPONENT','MISSING_ROUTING','MISSING_MACHINE','MACHINE_OVERLOAD','BATCH_RISK',"
                "'FLOW_GAP','VALVE_FLOW_IMBALANCE','EXTREME_DELAY','VENDOR_UNAVAILABLE','VENDOR_OVERLOADED'"
                ")"
            ),
            name="ck_flow_blockers_blocker_type",
        ),
        CheckConstraint("severity in ('INFO', 'WARNING', 'CRITICAL')", name="ck_flow_blockers_severity"),
        Index("ix_flow_blockers_run_blocker_type", "planning_run_id", "blocker_type"),
        Index("ix_flow_blockers_run_severity", "planning_run_id", "severity"),
        Index("ix_flow_blockers_run_valve", "planning_run_id", "valve_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    planned_operation_id: Mapped[str | None] = mapped_column(ForeignKey("planned_operations.id"), nullable=True)
    valve_id: Mapped[str | None] = mapped_column(String, nullable=True)
    component_line_no: Mapped[int | None] = mapped_column(nullable=True)
    component: Mapped[str | None] = mapped_column(String, nullable=True)
    operation_name: Mapped[str | None] = mapped_column(String, nullable=True)
    blocker_type: Mapped[str] = mapped_column(String, nullable=False)
    cause: Mapped[str] = mapped_column(String, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class ValveReadinessSummary(Base):
    __tablename__ = "valve_readiness_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["planning_run_id", "valve_id"],
            ["valves.planning_run_id", "valves.valve_id"],
            name="fk_valve_readiness_summaries_run_valve",
        ),
        UniqueConstraint("planning_run_id", "valve_id", name="uq_valve_readiness_summaries_run_valve"),
        CheckConstraint("value_cr >= 0", name="ck_valve_readiness_summaries_value_cr_nonnegative"),
        CheckConstraint("total_components >= 0", name="ck_valve_readiness_summaries_total_components_nonnegative"),
        CheckConstraint("ready_components >= 0", name="ck_valve_readiness_summaries_ready_components_nonnegative"),
        CheckConstraint("required_components >= 0", name="ck_valve_readiness_summaries_required_components_nonnegative"),
        CheckConstraint(
            "ready_required_count >= 0",
            name="ck_valve_readiness_summaries_ready_required_count_nonnegative",
        ),
        CheckConstraint(
            "pending_required_count >= 0",
            name="ck_valve_readiness_summaries_pending_required_count_nonnegative",
        ),
        CheckConstraint("full_kit_flag in (0, 1)", name="ck_valve_readiness_summaries_full_kit_flag_bool"),
        CheckConstraint("near_ready_flag in (0, 1)", name="ck_valve_readiness_summaries_near_ready_flag_bool"),
        CheckConstraint(
            "otd_delay_days >= 0",
            name="ck_valve_readiness_summaries_otd_delay_days_nonnegative",
        ),
        CheckConstraint("otd_risk_flag in (0, 1)", name="ck_valve_readiness_summaries_otd_risk_flag_bool"),
        CheckConstraint(
            "readiness_status in ('READY', 'NEAR_READY', 'NOT_READY', 'AT_RISK', 'DATA_INCOMPLETE')",
            name="ck_valve_readiness_summaries_readiness_status",
        ),
        CheckConstraint(
            "valve_flow_imbalance_flag in (0, 1)",
            name="ck_valve_readiness_summaries_valve_flow_imbalance_flag_bool",
        ),
        Index("ix_valve_readiness_summaries_run_status", "planning_run_id", "readiness_status"),
        Index("ix_valve_readiness_summaries_run_otd_risk", "planning_run_id", "otd_risk_flag"),
        Index("ix_valve_readiness_summaries_run_assembly_date", "planning_run_id", "assembly_date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    valve_id: Mapped[str] = mapped_column(String, nullable=False)
    customer: Mapped[str] = mapped_column(String, nullable=False)
    assembly_date: Mapped[str] = mapped_column(String, nullable=False)
    dispatch_date: Mapped[str] = mapped_column(String, nullable=False)
    value_cr: Mapped[float] = mapped_column(nullable=False)
    total_components: Mapped[int] = mapped_column(nullable=False)
    ready_components: Mapped[int] = mapped_column(nullable=False)
    required_components: Mapped[int] = mapped_column(nullable=False)
    ready_required_count: Mapped[int] = mapped_column(nullable=False)
    pending_required_count: Mapped[int] = mapped_column(nullable=False)
    full_kit_flag: Mapped[int] = mapped_column(nullable=False)
    near_ready_flag: Mapped[int] = mapped_column(nullable=False)
    valve_expected_completion_offset_days: Mapped[float | None] = mapped_column(nullable=True)
    valve_expected_completion_date: Mapped[str | None] = mapped_column(String, nullable=True)
    otd_delay_days: Mapped[float] = mapped_column(nullable=False)
    otd_risk_flag: Mapped[int] = mapped_column(nullable=False)
    readiness_status: Mapped[str] = mapped_column(String, nullable=False)
    risk_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    valve_flow_gap_days: Mapped[float | None] = mapped_column(nullable=True)
    valve_flow_imbalance_flag: Mapped[int] = mapped_column(nullable=False)
