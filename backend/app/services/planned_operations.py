from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.output import FlowBlocker, PlannedOperation
from app.planning.input_loader import PlanningSettingsOverride, load_planning_input
from app.planning.priority import calculate_component_priorities
from app.planning.readiness import calculate_component_readiness, calculate_valve_readiness
from app.planning.routing import expand_routing_operations


def calculate_and_persist_planned_operations(
    planning_run_id: str,
    db: Session,
    *,
    settings_override: PlanningSettingsOverride | None = None,
    commit: bool = True,
) -> tuple:
    planning_input = load_planning_input(
        planning_run_id=planning_run_id,
        db=db,
        settings_override=settings_override,
    )
    component_readiness = calculate_component_readiness(planning_input)
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)
    prioritized_components = calculate_component_priorities(
        planning_input=planning_input,
        component_readiness=component_readiness,
        valve_readiness=valve_readiness,
    )
    expansion = expand_routing_operations(
        planning_input=planning_input,
        prioritized_components=prioritized_components,
    )

    try:
        db.execute(delete(PlannedOperation).where(PlannedOperation.planning_run_id == planning_run_id))
        db.execute(
            delete(FlowBlocker).where(
                FlowBlocker.planning_run_id == planning_run_id,
                FlowBlocker.blocker_type == "MISSING_ROUTING",
            )
        )
        db.add_all(
            [
                PlannedOperation(
                    id=new_uuid(),
                    planning_run_id=planning_run_id,
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    operation_no=row.operation_no,
                    operation_name=row.operation_name,
                    machine_type=row.machine_type,
                    alt_machine=row.alt_machine,
                    qty=row.qty,
                    operation_hours=row.operation_hours,
                    availability_date=row.availability_date.isoformat(),
                    date_confidence=row.date_confidence,
                    priority_score=row.priority_score,
                    sort_sequence=row.sort_sequence,
                    availability_offset_days=row.availability_offset_days,
                    operation_arrival_offset_days=row.operation_arrival_offset_days,
                    operation_arrival_date=(
                        None if row.operation_arrival_date is None else row.operation_arrival_date.isoformat()
                    ),
                    scheduled_start_offset_days=row.scheduled_start_offset_days,
                    internal_wait_days=row.internal_wait_days,
                    processing_time_days=row.processing_time_days,
                    internal_completion_days=row.internal_completion_days,
                    internal_completion_offset_days=row.internal_completion_offset_days,
                    internal_completion_date=(
                        None if row.internal_completion_date is None else row.internal_completion_date.isoformat()
                    ),
                    extreme_delay_flag=(
                        None if row.extreme_delay_flag is None else (1 if row.extreme_delay_flag else 0)
                    ),
                    recommendation_status=row.recommendation_status,
                )
                for row in expansion.planned_operations
            ]
        )
        db.add_all(
            [
                FlowBlocker(
                    id=new_uuid(),
                    planning_run_id=planning_run_id,
                    planned_operation_id=row.planned_operation_id,
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    operation_name=row.operation_name,
                    blocker_type=row.blocker_type,
                    cause=row.cause,
                    recommended_action=row.recommended_action,
                    severity=row.severity,
                )
                for row in expansion.flow_blockers
            ]
        )
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise

    return expansion
