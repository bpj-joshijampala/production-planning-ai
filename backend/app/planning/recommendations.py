from dataclasses import dataclass
from datetime import date

from app.planning.same_day_arrival import calculate_same_day_arrival_load_days

VENDOR_MODEL_LIMIT_WARNING = "External pending load and vendor timing are only partially modeled in V1."


@dataclass(frozen=True, slots=True)
class PlannedOperationSnapshot:
    planned_operation_id: str
    valve_id: str
    component_line_no: int
    component: str
    operation_name: str
    machine_type: str
    alt_machine: str | None
    subcontract_allowed: bool
    vendor_process: str | None
    operation_hours: float
    operation_arrival_offset_days: float | None
    operation_arrival_date: date | None
    full_kit_flag: bool
    near_ready_flag: bool
    internal_wait_days: float | None
    processing_time_days: float | None
    internal_completion_days: float | None
    internal_completion_offset_days: float | None
    internal_completion_date: date | None
    extreme_delay_flag: bool | None


@dataclass(frozen=True, slots=True)
class MachineLoadSummarySnapshot:
    machine_type: str
    total_operation_hours: float
    capacity_hours_per_day: float
    load_days: float
    buffer_days: float
    spare_capacity_days: float
    overload_flag: bool
    batch_risk_flag: bool


@dataclass(frozen=True, slots=True)
class VendorSnapshot:
    vendor_id: str
    vendor_name: str
    primary_process: str
    turnaround_days: float
    transport_days_total: float
    effective_lead_days: float
    capacity_rating: str | None
    reliability: str | None
    approved: bool


@dataclass(frozen=True, slots=True)
class AlternateMachineFeasibility:
    suggested_machine_type: str
    alternate_load_days_after_assignment: float
    alternate_buffer_days: float


@dataclass(frozen=True, slots=True)
class SubcontractEvaluation:
    recommendation_type: str
    suggested_vendor_id: str | None
    suggested_vendor_name: str | None
    vendor_total_days: float | None
    vendor_completion_offset_days: float | None
    vendor_gain_days: float | None
    vendor_process_required: str
    failure_reason_code: str | None


@dataclass(frozen=True, slots=True)
class RecommendationData:
    planned_operation_id: str | None
    recommendation_type: str
    valve_id: str | None
    component_line_no: int | None
    component: str | None
    operation_name: str | None
    machine_type: str | None
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
    reason_codes: tuple[str, ...]
    explanation: str
    status: str
    recommendation_status: str


@dataclass(frozen=True, slots=True)
class RecommendationDraft:
    row: PlannedOperationSnapshot
    machine_summary: MachineLoadSummarySnapshot | None
    alternate_feasibility: AlternateMachineFeasibility | None
    subcontract_evaluation: SubcontractEvaluation | None
    recommendation_type: str
    priority_load_days_for_machine_type: float | None
    same_day_arrival_load_days: float | None


@dataclass(frozen=True, slots=True)
class VendorLoadSummaryData:
    vendor_id: str
    vendor_name: str
    primary_process: str
    vendor_recommended_jobs: int
    max_recommended_jobs_per_horizon: int
    selected_vendor_overloaded_flag: bool
    status: str


def calculate_placeholder_recommendations(
    *,
    planned_operations: tuple[PlannedOperationSnapshot, ...],
    machine_load_summaries: tuple[MachineLoadSummarySnapshot, ...],
    vendors: tuple[VendorSnapshot, ...],
) -> tuple[RecommendationData, ...]:
    machine_summaries = {row.machine_type: row for row in machine_load_summaries}
    priority_load_days_by_machine = _priority_load_days_by_machine(
        planned_operations=planned_operations,
        machine_summaries=machine_summaries,
    )
    projected_operation_hours_by_machine = {
        row.machine_type: row.total_operation_hours for row in machine_load_summaries
    }
    same_day_arrival_load_days_by_operation = _same_day_arrival_load_days_by_operation(
        planned_operations=planned_operations,
        machine_summaries=machine_summaries,
    )
    projected_subcontract_counts_by_vendor: dict[str, int] = {}
    recommendation_drafts: list[RecommendationDraft] = []

    for row in planned_operations:
        machine_summary = machine_summaries.get(row.machine_type)
        priority_load_days_for_machine_type = priority_load_days_by_machine.get(row.machine_type)
        alternate_feasibility = _alternate_machine_feasibility(
            row=row,
            machine_summaries=machine_summaries,
            primary_machine_summary=machine_summary,
            projected_operation_hours_by_machine=projected_operation_hours_by_machine,
        )
        subcontract_evaluation: SubcontractEvaluation | None = None
        recommendation_type = _placeholder_recommendation_type(
            row=row,
            machine_summary=machine_summary,
            priority_load_days_for_machine_type=priority_load_days_for_machine_type,
        )

        if recommendation_type == "MACHINE_OVERLOAD":
            if alternate_feasibility is not None:
                recommendation_type = "USE_ALTERNATE"
                projected_operation_hours_by_machine[alternate_feasibility.suggested_machine_type] = (
                    projected_operation_hours_by_machine.get(alternate_feasibility.suggested_machine_type, 0.0)
                    + row.operation_hours
                )
            else:
                subcontract_evaluation = _evaluate_subcontract(
                    row=row,
                    vendors=vendors,
                    projected_subcontract_counts_by_vendor=projected_subcontract_counts_by_vendor,
                )
                recommendation_type = subcontract_evaluation.recommendation_type
                if (
                    subcontract_evaluation.recommendation_type == "SUBCONTRACT"
                    and subcontract_evaluation.suggested_vendor_id is not None
                ):
                    projected_subcontract_counts_by_vendor[subcontract_evaluation.suggested_vendor_id] = (
                        projected_subcontract_counts_by_vendor.get(subcontract_evaluation.suggested_vendor_id, 0) + 1
                    )

        recommendation_drafts.append(
            RecommendationDraft(
                row=row,
                machine_summary=machine_summary,
                alternate_feasibility=alternate_feasibility,
                subcontract_evaluation=subcontract_evaluation,
                recommendation_type=recommendation_type,
                priority_load_days_for_machine_type=priority_load_days_for_machine_type,
                same_day_arrival_load_days=same_day_arrival_load_days_by_operation.get(row.planned_operation_id),
            )
        )

    batch_candidate_counts = _subcontract_batch_candidate_counts(recommendation_drafts)

    recommendations: list[RecommendationData] = []
    for draft in recommendation_drafts:
        batch_count = _batch_candidate_count(
            draft=draft,
            batch_candidate_counts=batch_candidate_counts,
        )
        batch_opportunity_flag = batch_count >= 2
        recommendation_type = _final_recommendation_type(
            recommendation_type=draft.recommendation_type,
            batch_opportunity_flag=batch_opportunity_flag,
        )
        recommendations.append(
            RecommendationData(
                planned_operation_id=draft.row.planned_operation_id,
                recommendation_type=recommendation_type,
                valve_id=draft.row.valve_id,
                component_line_no=draft.row.component_line_no,
                component=draft.row.component,
                operation_name=draft.row.operation_name,
                machine_type=draft.row.machine_type,
                suggested_machine_type=(
                    draft.alternate_feasibility.suggested_machine_type
                    if recommendation_type == "USE_ALTERNATE" and draft.alternate_feasibility is not None
                    else None
                ),
                suggested_vendor_id=(
                    draft.subcontract_evaluation.suggested_vendor_id
                    if draft.subcontract_evaluation is not None
                    else None
                ),
                suggested_vendor_name=(
                    draft.subcontract_evaluation.suggested_vendor_name
                    if draft.subcontract_evaluation is not None
                    else None
                ),
                internal_wait_days=draft.row.internal_wait_days,
                processing_time_days=draft.row.processing_time_days,
                internal_completion_days=draft.row.internal_completion_days,
                vendor_total_days=(
                    draft.subcontract_evaluation.vendor_total_days
                    if draft.subcontract_evaluation is not None
                    else None
                ),
                vendor_gain_days=(
                    draft.subcontract_evaluation.vendor_gain_days
                    if draft.subcontract_evaluation is not None
                    else None
                ),
                subcontract_batch_candidate_count=(batch_count if batch_opportunity_flag else None),
                batch_subcontract_opportunity_flag=batch_opportunity_flag,
                reason_codes=_reason_codes(
                    recommendation_type=recommendation_type,
                    alternate_feasibility=draft.alternate_feasibility,
                    subcontract_evaluation=draft.subcontract_evaluation,
                ),
                explanation=_recommendation_explanation(
                    recommendation_type=recommendation_type,
                    row=draft.row,
                    machine_summary=draft.machine_summary,
                    alternate_feasibility=draft.alternate_feasibility,
                    subcontract_evaluation=draft.subcontract_evaluation,
                    priority_load_days_for_machine_type=draft.priority_load_days_for_machine_type,
                    subcontract_batch_candidate_count=batch_count if batch_opportunity_flag else None,
                    same_day_arrival_load_days=draft.same_day_arrival_load_days,
                ),
                status="PENDING",
                recommendation_status=(
                    "SUBCONTRACT"
                    if recommendation_type == "BATCH_SUBCONTRACT_OPPORTUNITY"
                    else recommendation_type
                ),
            )
        )

    return tuple(recommendations)


def calculate_vendor_load_summaries(
    *,
    vendors: tuple[tuple[str, str, str, str | None], ...],
    recommendations: tuple[RecommendationData, ...],
) -> tuple[VendorLoadSummaryData, ...]:
    subcontract_counts: dict[str, int] = {}
    for recommendation in recommendations:
        if recommendation.recommendation_type not in {"SUBCONTRACT", "BATCH_SUBCONTRACT_OPPORTUNITY"}:
            continue
        if recommendation.suggested_vendor_id is None:
            continue
        subcontract_counts[recommendation.suggested_vendor_id] = subcontract_counts.get(recommendation.suggested_vendor_id, 0) + 1

    summaries = [
        VendorLoadSummaryData(
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            primary_process=primary_process,
            vendor_recommended_jobs=subcontract_counts.get(vendor_id, 0),
            max_recommended_jobs_per_horizon=_vendor_capacity_limit(capacity_rating),
            selected_vendor_overloaded_flag=subcontract_counts.get(vendor_id, 0) >= _vendor_capacity_limit(capacity_rating),
            status=(
                "VENDOR_OVERLOADED"
                if subcontract_counts.get(vendor_id, 0) >= _vendor_capacity_limit(capacity_rating)
                else "OK"
            ),
        )
        for vendor_id, vendor_name, primary_process, capacity_rating in sorted(vendors, key=lambda row: (row[0], row[2]))
    ]
    return tuple(summaries)


def _subcontract_batch_candidate_counts(
    recommendation_drafts: list[RecommendationDraft],
) -> dict[tuple[str, str, str], int]:
    counts: dict[tuple[str, str, str], int] = {}
    for draft in recommendation_drafts:
        key = _subcontract_batch_key(draft)
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _batch_candidate_count(
    *,
    draft: RecommendationDraft,
    batch_candidate_counts: dict[tuple[str, str, str], int],
) -> int:
    key = _subcontract_batch_key(draft)
    if key is None:
        return 0
    return batch_candidate_counts.get(key, 0)


def _subcontract_batch_key(draft: RecommendationDraft) -> tuple[str, str, str] | None:
    subcontract_evaluation = draft.subcontract_evaluation
    if subcontract_evaluation is None or subcontract_evaluation.suggested_vendor_id is None:
        return None
    if not _is_batch_subcontract_candidate(draft):
        return None
    return (
        _normalize_text(draft.row.machine_type),
        _normalize_text(subcontract_evaluation.vendor_process_required),
        subcontract_evaluation.suggested_vendor_id,
    )


def _is_batch_subcontract_candidate(draft: RecommendationDraft) -> bool:
    subcontract_evaluation = draft.subcontract_evaluation
    if subcontract_evaluation is None or subcontract_evaluation.suggested_vendor_id is None:
        return False
    if draft.recommendation_type == "SUBCONTRACT":
        return True
    return (
        draft.recommendation_type == "NO_FEASIBLE_OPTION"
        and subcontract_evaluation.failure_reason_code == "VENDOR_CAPACITY_REACHED"
        and subcontract_evaluation.vendor_gain_days is not None
        and subcontract_evaluation.vendor_gain_days > 0
    )


def _final_recommendation_type(
    *,
    recommendation_type: str,
    batch_opportunity_flag: bool,
) -> str:
    if recommendation_type == "SUBCONTRACT" and batch_opportunity_flag:
        return "BATCH_SUBCONTRACT_OPPORTUNITY"
    return recommendation_type


def _same_day_arrival_load_days_by_operation(
    *,
    planned_operations: tuple[PlannedOperationSnapshot, ...],
    machine_summaries: dict[str, MachineLoadSummarySnapshot],
) -> dict[str, float]:
    same_day_arrival_load_days_by_key = calculate_same_day_arrival_load_days(
        arrivals=tuple(
            (row.operation_arrival_date, row.machine_type, row.operation_hours)
            for row in planned_operations
            if row.operation_arrival_date is not None
        ),
        capacity_hours_per_day_by_machine={
            machine_type: machine_summary.capacity_hours_per_day
            for machine_type, machine_summary in machine_summaries.items()
        },
    )
    return {
        row.planned_operation_id: same_day_arrival_load_days_by_key[(row.operation_arrival_date.isoformat(), row.machine_type)]
        for row in planned_operations
        if row.operation_arrival_date is not None
        and row.machine_type in machine_summaries
        and machine_summaries[row.machine_type].capacity_hours_per_day > 0
    }


def _priority_load_days_by_machine(
    *,
    planned_operations: tuple[PlannedOperationSnapshot, ...],
    machine_summaries: dict[str, MachineLoadSummarySnapshot],
) -> dict[str, float]:
    priority_operation_hours_by_machine: dict[str, float] = {}
    for row in planned_operations:
        if not (row.full_kit_flag or row.near_ready_flag):
            continue
        priority_operation_hours_by_machine[row.machine_type] = (
            priority_operation_hours_by_machine.get(row.machine_type, 0.0) + row.operation_hours
        )

    return {
        machine_type: (
            0.0
            if machine_summary.capacity_hours_per_day <= 0
            else priority_operation_hours_by_machine.get(machine_type, 0.0) / machine_summary.capacity_hours_per_day
        )
        for machine_type, machine_summary in machine_summaries.items()
    }


def _placeholder_recommendation_type(
    *,
    row: PlannedOperationSnapshot,
    machine_summary: MachineLoadSummarySnapshot | None,
    priority_load_days_for_machine_type: float | None,
) -> str:
    if (
        row.internal_completion_date is None
        or row.internal_completion_days is None
        or row.internal_completion_offset_days is None
        or row.operation_arrival_offset_days is None
    ):
        return "DATA_ERROR"
    if row.extreme_delay_flag:
        return "EXTREME_DELAY"
    if _should_hold_for_priority_flow(
        row=row,
        machine_summary=machine_summary,
        priority_load_days_for_machine_type=priority_load_days_for_machine_type,
    ):
        return "HOLD_FOR_PRIORITY_FLOW"
    if machine_summary is not None and machine_summary.overload_flag:
        return "MACHINE_OVERLOAD"
    if machine_summary is not None and machine_summary.batch_risk_flag:
        return "BATCH_RISK"
    return "OK_INTERNAL"


def _alternate_machine_feasibility(
    *,
    row: PlannedOperationSnapshot,
    machine_summaries: dict[str, MachineLoadSummarySnapshot],
    primary_machine_summary: MachineLoadSummarySnapshot | None,
    projected_operation_hours_by_machine: dict[str, float],
) -> AlternateMachineFeasibility | None:
    if primary_machine_summary is None or not primary_machine_summary.overload_flag:
        return None

    alternate_machine = None if row.alt_machine is None else row.alt_machine.strip()
    if not alternate_machine or alternate_machine == row.machine_type:
        return None

    alternate_summary = machine_summaries.get(alternate_machine)
    if alternate_summary is None or alternate_summary.capacity_hours_per_day <= 0:
        return None

    alternate_load_days_after_assignment = (
        projected_operation_hours_by_machine.get(alternate_machine, alternate_summary.total_operation_hours)
        + row.operation_hours
    ) / alternate_summary.capacity_hours_per_day
    if alternate_load_days_after_assignment > alternate_summary.buffer_days:
        return None

    return AlternateMachineFeasibility(
        suggested_machine_type=alternate_machine,
        alternate_load_days_after_assignment=alternate_load_days_after_assignment,
        alternate_buffer_days=alternate_summary.buffer_days,
    )


def _should_hold_for_priority_flow(
    *,
    row: PlannedOperationSnapshot,
    machine_summary: MachineLoadSummarySnapshot | None,
    priority_load_days_for_machine_type: float | None,
) -> bool:
    if row.full_kit_flag or row.near_ready_flag:
        return False
    if machine_summary is None or row.processing_time_days is None:
        return False
    if priority_load_days_for_machine_type is None:
        return False

    return not (
        priority_load_days_for_machine_type <= machine_summary.buffer_days
        and machine_summary.spare_capacity_days >= row.processing_time_days
    )


def _evaluate_subcontract(
    *,
    row: PlannedOperationSnapshot,
    vendors: tuple[VendorSnapshot, ...],
    projected_subcontract_counts_by_vendor: dict[str, int],
) -> SubcontractEvaluation:
    vendor_process_required = _vendor_process_required(row)

    if not row.subcontract_allowed:
        return SubcontractEvaluation(
            recommendation_type="NO_FEASIBLE_OPTION",
            suggested_vendor_id=None,
            suggested_vendor_name=None,
            vendor_total_days=None,
            vendor_completion_offset_days=None,
            vendor_gain_days=None,
            vendor_process_required=vendor_process_required,
            failure_reason_code="SUBCONTRACT_NOT_ALLOWED",
        )

    candidate_vendors = _candidate_vendors(vendors=vendors, vendor_process_required=vendor_process_required)
    if not candidate_vendors:
        return SubcontractEvaluation(
            recommendation_type="NO_FEASIBLE_OPTION",
            suggested_vendor_id=None,
            suggested_vendor_name=None,
            vendor_total_days=None,
            vendor_completion_offset_days=None,
            vendor_gain_days=None,
            vendor_process_required=vendor_process_required,
            failure_reason_code="NO_APPROVED_VENDOR",
        )

    preferred_vendor = candidate_vendors[0]
    preferred_vendor_total_days = _vendor_total_days(preferred_vendor)
    preferred_vendor_completion_offset_days = (row.operation_arrival_offset_days or 0.0) + preferred_vendor_total_days
    preferred_vendor_gain_days = (
        None
        if row.internal_completion_offset_days is None
        else row.internal_completion_offset_days - preferred_vendor_completion_offset_days
    )

    selected_vendor = next(
        (
            vendor
            for vendor in candidate_vendors
            if projected_subcontract_counts_by_vendor.get(vendor.vendor_id, 0)
            < _vendor_capacity_limit(vendor.capacity_rating)
        ),
        None,
    )
    if selected_vendor is None:
        if (
            row.internal_completion_offset_days is not None
            and preferred_vendor_completion_offset_days < row.internal_completion_offset_days
        ):
            return SubcontractEvaluation(
                recommendation_type="NO_FEASIBLE_OPTION",
                suggested_vendor_id=preferred_vendor.vendor_id,
                suggested_vendor_name=preferred_vendor.vendor_name,
                vendor_total_days=preferred_vendor_total_days,
                vendor_completion_offset_days=preferred_vendor_completion_offset_days,
                vendor_gain_days=preferred_vendor_gain_days,
                vendor_process_required=vendor_process_required,
                failure_reason_code="VENDOR_CAPACITY_REACHED",
            )
        return SubcontractEvaluation(
            recommendation_type="NO_FEASIBLE_OPTION",
            suggested_vendor_id=None,
            suggested_vendor_name=None,
            vendor_total_days=None,
            vendor_completion_offset_days=None,
            vendor_gain_days=None,
            vendor_process_required=vendor_process_required,
            failure_reason_code="VENDOR_CAPACITY_REACHED",
        )

    vendor_total_days = _vendor_total_days(selected_vendor)
    vendor_completion_offset_days = (row.operation_arrival_offset_days or 0.0) + vendor_total_days

    if row.internal_completion_offset_days is not None and vendor_completion_offset_days < row.internal_completion_offset_days:
        return SubcontractEvaluation(
            recommendation_type="SUBCONTRACT",
            suggested_vendor_id=selected_vendor.vendor_id,
            suggested_vendor_name=selected_vendor.vendor_name,
            vendor_total_days=vendor_total_days,
            vendor_completion_offset_days=vendor_completion_offset_days,
            vendor_gain_days=row.internal_completion_offset_days - vendor_completion_offset_days,
            vendor_process_required=vendor_process_required,
            failure_reason_code=None,
        )

    return SubcontractEvaluation(
        recommendation_type="NO_FEASIBLE_OPTION",
        suggested_vendor_id=selected_vendor.vendor_id,
        suggested_vendor_name=selected_vendor.vendor_name,
        vendor_total_days=vendor_total_days,
        vendor_completion_offset_days=vendor_completion_offset_days,
        vendor_gain_days=None,
        vendor_process_required=vendor_process_required,
        failure_reason_code="VENDOR_NOT_FASTER",
    )


def _candidate_vendors(
    *,
    vendors: tuple[VendorSnapshot, ...],
    vendor_process_required: str,
) -> tuple[VendorSnapshot, ...]:
    process_key = _normalize_text(vendor_process_required)
    candidates = [
        vendor
        for vendor in vendors
        if vendor.approved and _normalize_text(vendor.primary_process) == process_key
    ]
    return tuple(
        sorted(
            candidates,
            key=lambda vendor: (
                _vendor_total_days(vendor),
                _reliability_rank(vendor.reliability),
                _capacity_rank(vendor.capacity_rating),
                vendor.vendor_id,
            ),
        )
    )


def _reason_codes(
    *,
    recommendation_type: str,
    alternate_feasibility: AlternateMachineFeasibility | None,
    subcontract_evaluation: SubcontractEvaluation | None,
) -> tuple[str, ...]:
    if recommendation_type == "BATCH_SUBCONTRACT_OPPORTUNITY" and subcontract_evaluation is not None:
        return ("PRIMARY_OVERLOADED", "SUBCONTRACT_FEASIBLE", "BATCH_SUBCONTRACT_OPPORTUNITY")
    if recommendation_type == "USE_ALTERNATE" and alternate_feasibility is not None:
        return ("PRIMARY_OVERLOADED", "ALTERNATE_FEASIBLE")
    if recommendation_type == "SUBCONTRACT" and subcontract_evaluation is not None:
        return ("PRIMARY_OVERLOADED", "SUBCONTRACT_FEASIBLE")
    if recommendation_type == "NO_FEASIBLE_OPTION" and subcontract_evaluation is not None:
        return (
            "NO_FEASIBLE_OPTION",
            subcontract_evaluation.failure_reason_code or "NO_FEASIBLE_OPTION",
        )
    if recommendation_type == "HOLD_FOR_PRIORITY_FLOW":
        return ("HOLD_FOR_PRIORITY_FLOW",)
    return (recommendation_type,)


def _recommendation_explanation(
    *,
    recommendation_type: str,
    row: PlannedOperationSnapshot,
    machine_summary: MachineLoadSummarySnapshot | None,
    alternate_feasibility: AlternateMachineFeasibility | None,
    subcontract_evaluation: SubcontractEvaluation | None,
    priority_load_days_for_machine_type: float | None,
    subcontract_batch_candidate_count: int | None = None,
    same_day_arrival_load_days: float | None = None,
) -> str:
    if recommendation_type == "DATA_ERROR":
        return "Operation cannot be completed because queue or machine-capacity data is incomplete."
    if recommendation_type == "EXTREME_DELAY":
        return (
            f"Operation wait {row.internal_wait_days or 0.0:.2f} days exceeds the configured extreme-delay threshold."
        )
    if recommendation_type == "HOLD_FOR_PRIORITY_FLOW" and machine_summary is not None:
        return (
            f"Machine_Type {row.machine_type} priority_load_days {priority_load_days_for_machine_type or 0.0:.2f} "
            f"must be protected within buffer_days {machine_summary.buffer_days:.2f}. "
            f"Spare_capacity_days {machine_summary.spare_capacity_days:.2f} is compared to "
            f"processing_time_days {row.processing_time_days or 0.0:.2f} for non-full-kit work. "
            "Hold this operation for priority flow."
        )
    if recommendation_type == "USE_ALTERNATE" and machine_summary is not None and alternate_feasibility is not None:
        return (
            f"Machine_Type {row.machine_type} load_days {machine_summary.load_days:.2f} exceeds "
            f"buffer_days {machine_summary.buffer_days:.2f}. "
            f"{alternate_feasibility.suggested_machine_type} load_days after assignment "
            f"{alternate_feasibility.alternate_load_days_after_assignment:.2f} stays within "
            f"buffer_days {alternate_feasibility.alternate_buffer_days:.2f}."
        )
    if recommendation_type == "SUBCONTRACT" and machine_summary is not None and subcontract_evaluation is not None:
        return (
            f"Machine_Type {row.machine_type} load_days {machine_summary.load_days:.2f} exceeds "
            f"buffer_days {machine_summary.buffer_days:.2f}. "
            f"Vendor {subcontract_evaluation.suggested_vendor_name} total_days "
            f"{subcontract_evaluation.vendor_total_days or 0.0:.2f} beats internal completion "
            f"{row.internal_completion_offset_days or 0.0:.2f} by "
            f"{subcontract_evaluation.vendor_gain_days or 0.0:.2f} days. "
            f"Send component directly to vendor on receipt. {VENDOR_MODEL_LIMIT_WARNING}"
        )
    if (
        recommendation_type == "BATCH_SUBCONTRACT_OPPORTUNITY"
        and machine_summary is not None
        and subcontract_evaluation is not None
    ):
        return (
            f"Machine_Type {row.machine_type} load_days {machine_summary.load_days:.2f} exceeds "
            f"buffer_days {machine_summary.buffer_days:.2f}. "
            f"Vendor {subcontract_evaluation.suggested_vendor_name} total_days "
            f"{subcontract_evaluation.vendor_total_days or 0.0:.2f} beats internal completion "
            f"{row.internal_completion_offset_days or 0.0:.2f} by "
            f"{subcontract_evaluation.vendor_gain_days or 0.0:.2f} days. "
            f"Batch opportunity candidate_count {subcontract_batch_candidate_count or 0} exists for "
            f"Machine_Type {row.machine_type}, process {subcontract_evaluation.vendor_process_required}, "
            f"and vendor {subcontract_evaluation.suggested_vendor_id}. "
            f"V1 flags the batching opportunity only and does not automatically group dispatches. "
            f"Send component directly to vendor on receipt. {VENDOR_MODEL_LIMIT_WARNING}"
        )
    if recommendation_type == "NO_FEASIBLE_OPTION" and machine_summary is not None and subcontract_evaluation is not None:
        prefix = (
            f"Machine_Type {row.machine_type} load_days {machine_summary.load_days:.2f} exceeds "
            f"buffer_days {machine_summary.buffer_days:.2f}. "
        )
        if subcontract_evaluation.failure_reason_code == "SUBCONTRACT_NOT_ALLOWED":
            return prefix + "Routing does not allow subcontracting for this operation."
        if subcontract_evaluation.failure_reason_code == "NO_APPROVED_VENDOR":
            return (
                prefix
                + f"No approved vendor exists for process {subcontract_evaluation.vendor_process_required}."
            )
        if subcontract_evaluation.failure_reason_code == "VENDOR_CAPACITY_REACHED":
            if (
                subcontract_evaluation.suggested_vendor_name is not None
                and subcontract_evaluation.vendor_total_days is not None
                and row.internal_completion_offset_days is not None
                and subcontract_evaluation.vendor_gain_days is not None
            ):
                return (
                    prefix
                    + f"Best approved vendor {subcontract_evaluation.suggested_vendor_name} total_days "
                    f"{subcontract_evaluation.vendor_total_days:.2f} would beat internal completion "
                    f"{row.internal_completion_offset_days:.2f} by "
                    f"{subcontract_evaluation.vendor_gain_days:.2f} days, but approved vendors for process "
                    f"{subcontract_evaluation.vendor_process_required} are already at the current-run modeled capacity limit. "
                    + VENDOR_MODEL_LIMIT_WARNING
                )
            return (
                prefix
                + f"Approved vendors for process {subcontract_evaluation.vendor_process_required} are already at the current-run modeled capacity limit. "
                + VENDOR_MODEL_LIMIT_WARNING
            )
        if subcontract_evaluation.failure_reason_code == "VENDOR_NOT_FASTER":
            return (
                prefix
                + f"Best approved vendor {subcontract_evaluation.suggested_vendor_name} total_days "
                f"{subcontract_evaluation.vendor_total_days or 0.0:.2f} does not beat internal completion "
                f"{row.internal_completion_offset_days or 0.0:.2f}. {VENDOR_MODEL_LIMIT_WARNING}"
            )
        return prefix + "No feasible alternate or subcontract option is currently available."
    if recommendation_type == "MACHINE_OVERLOAD" and machine_summary is not None:
        return (
            f"Machine_Type {row.machine_type} load_days {machine_summary.load_days:.2f} exceeds "
            f"buffer_days {machine_summary.buffer_days:.2f}."
        )
    if recommendation_type == "BATCH_RISK":
        load_days_text = (
            "unknown"
            if same_day_arrival_load_days is None
            else f"{same_day_arrival_load_days:.2f}"
        )
        arrival_date_text = (
            ""
            if row.operation_arrival_date is None
            else f" on {row.operation_arrival_date.isoformat()}"
        )
        return (
            f"Machine_Type {row.machine_type} same_day_arrival_load_days {load_days_text}"
            f"{arrival_date_text} exceeds threshold 1.00 and requires planner review."
        )
    return "Operation can remain on the current internal path under the current planning rules."


def _vendor_process_required(row: PlannedOperationSnapshot) -> str:
    vendor_process = _normalize_text(row.vendor_process)
    return vendor_process if vendor_process else _normalize_text(row.machine_type)


def _vendor_total_days(vendor: VendorSnapshot) -> float:
    if vendor.effective_lead_days > 0:
        return vendor.effective_lead_days
    return vendor.turnaround_days + vendor.transport_days_total


def _reliability_rank(reliability: str | None) -> int:
    normalized = _normalize_text(reliability)
    return {"A": 0, "B": 1, "C": 2}.get(normalized, 3)


def _capacity_rank(capacity_rating: str | None) -> int:
    normalized = _normalize_text(capacity_rating)
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(normalized, 3)


def _normalize_text(value: str | None) -> str:
    return "" if value is None else value.strip().upper()


def _vendor_capacity_limit(capacity_rating: str | None) -> int:
    normalized = _normalize_text(capacity_rating)
    if normalized == "HIGH":
        return 5
    if normalized == "MEDIUM":
        return 3
    return 1
