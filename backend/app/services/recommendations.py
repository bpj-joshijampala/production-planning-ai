import json
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.canonical import RoutingOperation, Vendor
from app.models.output import FlowBlocker, MachineLoadSummary, PlannedOperation, Recommendation, ValveReadinessSummary, VendorLoadSummary
from app.planning.recommendations import (
    MachineLoadSummarySnapshot,
    PlannedOperationSnapshot,
    RecommendationData,
    VendorSnapshot,
    calculate_placeholder_recommendations,
    calculate_vendor_load_summaries,
)


class RecommendationPersistenceResult:
    def __init__(
        self,
        *,
        recommendations: tuple[RecommendationData, ...],
        vendor_load_summaries,
    ) -> None:
        self.recommendations = recommendations
        self.vendor_load_summaries = vendor_load_summaries


def calculate_and_persist_placeholder_recommendations(
    planning_run_id: str,
    db: Session,
    *,
    commit: bool = True,
) -> RecommendationPersistenceResult:
    planned_operations = list(
        db.scalars(
            select(PlannedOperation)
            .where(PlannedOperation.planning_run_id == planning_run_id)
            .order_by(PlannedOperation.sort_sequence.asc(), PlannedOperation.operation_no.asc())
        )
    )
    machine_load_summaries = list(
        db.scalars(
            select(MachineLoadSummary)
            .where(MachineLoadSummary.planning_run_id == planning_run_id)
            .order_by(MachineLoadSummary.machine_type.asc())
        )
    )
    vendors = list(
        db.scalars(
            select(Vendor)
            .where(Vendor.planning_run_id == planning_run_id)
            .order_by(Vendor.vendor_id.asc())
        )
    )
    routing_operations = list(
        db.scalars(
            select(RoutingOperation)
            .where(RoutingOperation.planning_run_id == planning_run_id)
            .order_by(RoutingOperation.component.asc(), RoutingOperation.operation_no.asc())
        )
    )
    valve_readiness_by_id = {
        row.valve_id: row
        for row in db.scalars(
            select(ValveReadinessSummary).where(ValveReadinessSummary.planning_run_id == planning_run_id)
        )
    }
    routing_by_component_operation = {
        (row.component, row.operation_no): row for row in routing_operations
    }

    recommendations = calculate_placeholder_recommendations(
        planned_operations=tuple(
            _to_planned_operation_snapshot(
                row,
                routing_by_component_operation.get((row.component, row.operation_no)),
                valve_readiness_by_id.get(row.valve_id),
            )
            for row in planned_operations
        ),
        machine_load_summaries=tuple(_to_machine_load_summary_snapshot(row) for row in machine_load_summaries),
        vendors=tuple(_to_vendor_snapshot(row) for row in vendors),
    )
    vendor_load_summaries = calculate_vendor_load_summaries(
        vendors=tuple((row.vendor_id, row.vendor_name, row.primary_process, row.capacity_rating) for row in vendors),
        recommendations=recommendations,
    )
    assembly_risk_by_valve = {
        row.valve_id: bool(row.otd_risk_flag)
        for row in db.scalars(
            select(ValveReadinessSummary).where(ValveReadinessSummary.planning_run_id == planning_run_id)
        )
    }
    vendor_unavailable_blockers = _vendor_unavailable_blockers(
        planning_run_id=planning_run_id,
        recommendations=recommendations,
        assembly_risk_by_valve=assembly_risk_by_valve,
    )
    vendor_overloaded_blockers = _vendor_overloaded_blockers(
        planning_run_id=planning_run_id,
        vendor_load_summaries=vendor_load_summaries,
    )

    try:
        db.execute(delete(Recommendation).where(Recommendation.planning_run_id == planning_run_id))
        db.execute(delete(VendorLoadSummary).where(VendorLoadSummary.planning_run_id == planning_run_id))
        db.execute(
            delete(FlowBlocker).where(
                FlowBlocker.planning_run_id == planning_run_id,
                FlowBlocker.blocker_type == "VENDOR_UNAVAILABLE",
            )
        )
        db.execute(
            delete(FlowBlocker).where(
                FlowBlocker.planning_run_id == planning_run_id,
                FlowBlocker.blocker_type == "VENDOR_OVERLOADED",
            )
        )

        recommendation_status_by_operation_id = {
            row.planned_operation_id: row.recommendation_status
            for row in recommendations
            if row.planned_operation_id is not None
        }
        for planned_operation in planned_operations:
            planned_operation.recommendation_status = recommendation_status_by_operation_id.get(planned_operation.id)

        db.add_all(
            [
                Recommendation(
                    id=new_uuid(),
                    planning_run_id=planning_run_id,
                    planned_operation_id=row.planned_operation_id,
                    recommendation_type=row.recommendation_type,
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    operation_name=row.operation_name,
                    machine_type=row.machine_type,
                    suggested_machine_type=row.suggested_machine_type,
                    suggested_vendor_id=row.suggested_vendor_id,
                    suggested_vendor_name=row.suggested_vendor_name,
                    internal_wait_days=row.internal_wait_days,
                    processing_time_days=row.processing_time_days,
                    internal_completion_days=row.internal_completion_days,
                    vendor_total_days=row.vendor_total_days,
                    vendor_gain_days=row.vendor_gain_days,
                    subcontract_batch_candidate_count=row.subcontract_batch_candidate_count,
                    batch_subcontract_opportunity_flag=1 if row.batch_subcontract_opportunity_flag else 0,
                    reason_codes_json=json.dumps(list(row.reason_codes), ensure_ascii=True, separators=(",", ":")),
                    explanation=row.explanation,
                    status=row.status,
                )
                for row in recommendations
            ]
        )
        db.add_all(
            [
                VendorLoadSummary(
                    id=new_uuid(),
                    planning_run_id=planning_run_id,
                    vendor_id=row.vendor_id,
                    vendor_name=row.vendor_name,
                    primary_process=row.primary_process,
                    vendor_recommended_jobs=row.vendor_recommended_jobs,
                    max_recommended_jobs_per_horizon=row.max_recommended_jobs_per_horizon,
                    selected_vendor_overloaded_flag=1 if row.selected_vendor_overloaded_flag else 0,
                    status=row.status,
                )
                for row in vendor_load_summaries
            ]
        )
        db.add_all(vendor_unavailable_blockers)
        db.add_all(vendor_overloaded_blockers)
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise

    return RecommendationPersistenceResult(
        recommendations=recommendations,
        vendor_load_summaries=vendor_load_summaries,
    )


def _to_planned_operation_snapshot(
    row: PlannedOperation,
    routing_row: RoutingOperation | None,
    valve_readiness_row: ValveReadinessSummary | None,
) -> PlannedOperationSnapshot:
    return PlannedOperationSnapshot(
        planned_operation_id=row.id,
        valve_id=row.valve_id,
        component_line_no=row.component_line_no,
        component=row.component,
        operation_name=row.operation_name,
        machine_type=row.machine_type,
        alt_machine=row.alt_machine,
        subcontract_allowed=False if routing_row is None else bool(routing_row.subcontract_allowed),
        vendor_process=None if routing_row is None else routing_row.vendor_process,
        operation_hours=row.operation_hours,
        operation_arrival_offset_days=row.operation_arrival_offset_days,
        operation_arrival_date=_parse_optional_date(row.operation_arrival_date),
        full_kit_flag=False if valve_readiness_row is None else bool(valve_readiness_row.full_kit_flag),
        near_ready_flag=False if valve_readiness_row is None else bool(valve_readiness_row.near_ready_flag),
        internal_wait_days=row.internal_wait_days,
        processing_time_days=row.processing_time_days,
        internal_completion_days=row.internal_completion_days,
        internal_completion_offset_days=row.internal_completion_offset_days,
        internal_completion_date=_parse_optional_date(row.internal_completion_date),
        extreme_delay_flag=None if row.extreme_delay_flag is None else bool(row.extreme_delay_flag),
    )


def _to_machine_load_summary_snapshot(row: MachineLoadSummary) -> MachineLoadSummarySnapshot:
    return MachineLoadSummarySnapshot(
        machine_type=row.machine_type,
        total_operation_hours=row.total_operation_hours,
        capacity_hours_per_day=row.capacity_hours_per_day,
        load_days=row.load_days,
        buffer_days=row.buffer_days,
        spare_capacity_days=row.spare_capacity_days,
        overload_flag=bool(row.overload_flag),
        batch_risk_flag=bool(row.batch_risk_flag),
    )


def _to_vendor_snapshot(row: Vendor) -> VendorSnapshot:
    return VendorSnapshot(
        vendor_id=row.vendor_id,
        vendor_name=row.vendor_name,
        primary_process=row.primary_process,
        turnaround_days=row.turnaround_days,
        transport_days_total=row.transport_days_total,
        effective_lead_days=row.effective_lead_days,
        capacity_rating=row.capacity_rating,
        reliability=row.reliability,
        approved=bool(row.approved),
    )


def _parse_optional_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _vendor_unavailable_blockers(
    *,
    planning_run_id: str,
    recommendations: tuple[RecommendationData, ...],
    assembly_risk_by_valve: dict[str, bool],
) -> list[FlowBlocker]:
    return [
        FlowBlocker(
            id=new_uuid(),
            planning_run_id=planning_run_id,
            planned_operation_id=row.planned_operation_id,
            valve_id=row.valve_id,
            component_line_no=row.component_line_no,
            component=row.component,
            operation_name=row.operation_name,
            blocker_type="VENDOR_UNAVAILABLE",
            cause=row.explanation,
            recommended_action=_vendor_unavailable_action(row),
            severity=_vendor_unavailable_severity(
                valve_id=row.valve_id,
                assembly_risk_by_valve=assembly_risk_by_valve,
            ),
        )
        for row in recommendations
        if _should_create_vendor_unavailable_blocker(row)
    ]


def _should_create_vendor_unavailable_blocker(row: RecommendationData) -> bool:
    if row.recommendation_type != "NO_FEASIBLE_OPTION":
        return False
    failure_reason = row.reason_codes[1] if len(row.reason_codes) > 1 else None
    return failure_reason == "NO_APPROVED_VENDOR"


def _vendor_unavailable_action(row: RecommendationData) -> str:
    failure_reason = row.reason_codes[1] if len(row.reason_codes) > 1 else None
    if failure_reason == "NO_APPROVED_VENDOR":
        return "Add an approved vendor for this process or keep the operation in-house with escalation."
    return "Review vendor availability and resolve the no-feasible-option path before execution."


def _vendor_unavailable_severity(
    *,
    valve_id: str | None,
    assembly_risk_by_valve: dict[str, bool],
) -> str:
    if valve_id is not None and assembly_risk_by_valve.get(valve_id, False):
        return "CRITICAL"
    return "WARNING"


def _vendor_overloaded_blockers(
    *,
    planning_run_id: str,
    vendor_load_summaries,
) -> list[FlowBlocker]:
    return [
        FlowBlocker(
            id=new_uuid(),
            planning_run_id=planning_run_id,
            planned_operation_id=None,
            valve_id=None,
            component_line_no=None,
            component=None,
            operation_name=None,
            blocker_type="VENDOR_OVERLOADED",
            cause=(
                f"Vendor {row.vendor_name} recommended_jobs {row.vendor_recommended_jobs} reached modeled limit "
                f"{row.max_recommended_jobs_per_horizon} for process {row.primary_process}."
            ),
            recommended_action=(
                f"Review vendor {row.vendor_name} load and dispatch timing before release. "
                "External pending load and vendor timing are only partially modeled in V1."
            ),
            severity="WARNING",
        )
        for row in vendor_load_summaries
        if row.selected_vendor_overloaded_flag
    ]
