import json
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.canonical import Vendor
from app.models.output import MachineLoadSummary, PlannedOperation, Recommendation, VendorLoadSummary
from app.planning.recommendations import (
    MachineLoadSummarySnapshot,
    PlannedOperationSnapshot,
    RecommendationData,
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

    recommendations = calculate_placeholder_recommendations(
        planned_operations=tuple(_to_planned_operation_snapshot(row) for row in planned_operations),
        machine_load_summaries=tuple(_to_machine_load_summary_snapshot(row) for row in machine_load_summaries),
    )
    vendor_load_summaries = calculate_vendor_load_summaries(
        vendors=tuple((row.vendor_id, row.vendor_name, row.primary_process, row.capacity_rating) for row in vendors),
        recommendations=recommendations,
    )

    try:
        db.execute(delete(Recommendation).where(Recommendation.planning_run_id == planning_run_id))
        db.execute(delete(VendorLoadSummary).where(VendorLoadSummary.planning_run_id == planning_run_id))

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


def _to_planned_operation_snapshot(row: PlannedOperation) -> PlannedOperationSnapshot:
    return PlannedOperationSnapshot(
        planned_operation_id=row.id,
        valve_id=row.valve_id,
        component_line_no=row.component_line_no,
        component=row.component,
        operation_name=row.operation_name,
        machine_type=row.machine_type,
        internal_wait_days=row.internal_wait_days,
        processing_time_days=row.processing_time_days,
        internal_completion_days=row.internal_completion_days,
        internal_completion_date=_parse_optional_date(row.internal_completion_date),
        extreme_delay_flag=None if row.extreme_delay_flag is None else bool(row.extreme_delay_flag),
    )


def _to_machine_load_summary_snapshot(row: MachineLoadSummary) -> MachineLoadSummarySnapshot:
    return MachineLoadSummarySnapshot(
        machine_type=row.machine_type,
        load_days=row.load_days,
        buffer_days=row.buffer_days,
        overload_flag=bool(row.overload_flag),
        batch_risk_flag=bool(row.batch_risk_flag),
    )


def _parse_optional_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)
