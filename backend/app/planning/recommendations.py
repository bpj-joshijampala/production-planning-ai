from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class PlannedOperationSnapshot:
    planned_operation_id: str
    valve_id: str
    component_line_no: int
    component: str
    operation_name: str
    machine_type: str
    internal_wait_days: float | None
    processing_time_days: float | None
    internal_completion_days: float | None
    internal_completion_date: date | None
    extreme_delay_flag: bool | None


@dataclass(frozen=True, slots=True)
class MachineLoadSummarySnapshot:
    machine_type: str
    load_days: float
    buffer_days: float
    overload_flag: bool
    batch_risk_flag: bool


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
) -> tuple[RecommendationData, ...]:
    machine_summaries = {row.machine_type: row for row in machine_load_summaries}
    recommendations: list[RecommendationData] = []

    for row in planned_operations:
        machine_summary = machine_summaries.get(row.machine_type)
        recommendation_type = _placeholder_recommendation_type(row=row, machine_summary=machine_summary)
        recommendations.append(
            RecommendationData(
                planned_operation_id=row.planned_operation_id,
                recommendation_type=recommendation_type,
                valve_id=row.valve_id,
                component_line_no=row.component_line_no,
                component=row.component,
                operation_name=row.operation_name,
                machine_type=row.machine_type,
                suggested_machine_type=None,
                suggested_vendor_id=None,
                suggested_vendor_name=None,
                internal_wait_days=row.internal_wait_days,
                processing_time_days=row.processing_time_days,
                internal_completion_days=row.internal_completion_days,
                vendor_total_days=None,
                vendor_gain_days=None,
                subcontract_batch_candidate_count=None,
                batch_subcontract_opportunity_flag=False,
                reason_codes=(recommendation_type,),
                explanation=_placeholder_explanation(
                    recommendation_type=recommendation_type,
                    row=row,
                    machine_summary=machine_summary,
                ),
                status="PENDING",
                recommendation_status=recommendation_type,
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
        if recommendation.recommendation_type != "SUBCONTRACT":
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


def _placeholder_recommendation_type(
    *,
    row: PlannedOperationSnapshot,
    machine_summary: MachineLoadSummarySnapshot | None,
) -> str:
    if row.internal_completion_date is None:
        return "DATA_ERROR"
    if row.extreme_delay_flag:
        return "EXTREME_DELAY"
    if machine_summary is not None and machine_summary.overload_flag:
        return "MACHINE_OVERLOAD"
    if machine_summary is not None and machine_summary.batch_risk_flag:
        return "BATCH_RISK"
    return "OK_INTERNAL"


def _placeholder_explanation(
    *,
    recommendation_type: str,
    row: PlannedOperationSnapshot,
    machine_summary: MachineLoadSummarySnapshot | None,
) -> str:
    if recommendation_type == "DATA_ERROR":
        return "Operation cannot be completed because queue or machine-capacity data is incomplete."
    if recommendation_type == "EXTREME_DELAY":
        return (
            f"Operation wait {row.internal_wait_days or 0.0:.2f} days exceeds the configured extreme-delay threshold."
        )
    if recommendation_type == "MACHINE_OVERLOAD" and machine_summary is not None:
        return (
            f"Machine_Type {row.machine_type} load_days {machine_summary.load_days:.2f} exceeds "
            f"buffer_days {machine_summary.buffer_days:.2f}."
        )
    if recommendation_type == "BATCH_RISK":
        return f"Machine_Type {row.machine_type} has same-day arrival pressure that requires planner review."
    return "Operation can remain on the current internal path based on current M2 placeholder rules."


def _vendor_capacity_limit(capacity_rating: str | None) -> int:
    normalized = "" if capacity_rating is None else capacity_rating.strip().upper()
    if normalized == "HIGH":
        return 5
    if normalized == "MEDIUM":
        return 3
    return 1
