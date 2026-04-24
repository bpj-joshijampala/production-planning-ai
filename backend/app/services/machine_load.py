from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.output import FlowBlocker, MachineLoadSummary, PlannedOperation
from app.planning.input_loader import PlanningSettingsOverride, load_planning_input
from app.planning.priority import calculate_component_priorities
from app.planning.queue import QueueSimulationResult, simulate_queue_and_machine_load
from app.planning.readiness import ComponentKey, calculate_component_readiness, calculate_valve_readiness
from app.planning.routing import expand_routing_operations
from app.services.valve_readiness import calculate_and_persist_valve_readiness


def calculate_and_persist_machine_load(
    planning_run_id: str,
    db: Session,
    *,
    settings_override: PlanningSettingsOverride | None = None,
    commit: bool = True,
) -> QueueSimulationResult:
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
    simulation = simulate_queue_and_machine_load(
        planning_input=planning_input,
        planned_operations=expansion.planned_operations,
        existing_flow_blockers=expansion.flow_blockers,
    )

    try:
        db.execute(delete(PlannedOperation).where(PlannedOperation.planning_run_id == planning_run_id))
        db.execute(
            delete(FlowBlocker).where(
                FlowBlocker.planning_run_id == planning_run_id,
                FlowBlocker.blocker_type.in_(
                    ("MISSING_ROUTING", "MISSING_MACHINE", "MACHINE_OVERLOAD", "BATCH_RISK", "EXTREME_DELAY")
                ),
            )
        )
        db.execute(delete(MachineLoadSummary).where(MachineLoadSummary.planning_run_id == planning_run_id))

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
                for row in simulation.planned_operations
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
                for row in simulation.flow_blockers
            ]
        )
        db.add_all(
            [
                MachineLoadSummary(
                    id=new_uuid(),
                    planning_run_id=planning_run_id,
                    machine_type=row.machine_type,
                    total_operation_hours=row.total_operation_hours,
                    capacity_hours_per_day=row.capacity_hours_per_day,
                    load_days=row.load_days,
                    buffer_days=row.buffer_days,
                    overload_flag=1 if row.overload_flag else 0,
                    overload_days=row.overload_days,
                    spare_capacity_days=row.spare_capacity_days,
                    underutilized_flag=1 if row.underutilized_flag else 0,
                    batch_risk_flag=1 if row.batch_risk_flag else 0,
                    status=row.status,
                )
                for row in simulation.machine_load_summaries
            ]
        )
        calculate_and_persist_valve_readiness(
            planning_run_id=planning_run_id,
            db=db,
            settings_override=settings_override,
            component_completion_offsets=_component_completion_offsets(
                planning_input=planning_input,
                simulation=simulation,
            ),
            commit=False,
        )
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise

    return simulation


def _component_completion_offsets(
    *,
    planning_input,
    simulation: QueueSimulationResult,
) -> dict[ComponentKey, float | None]:
    offsets: dict[ComponentKey, float | None] = {}
    offsets_by_component: dict[ComponentKey, list[float | None]] = {}

    for row in simulation.planned_operations:
        key = ComponentKey(valve_id=row.valve_id, component_line_no=row.component_line_no)
        offsets_by_component.setdefault(key, []).append(row.internal_completion_offset_days)

    for key, completion_offsets in offsets_by_component.items():
        if any(offset is None for offset in completion_offsets):
            offsets[key] = None
            continue
        offsets[key] = max(offset for offset in completion_offsets if offset is not None)

    for blocker in simulation.flow_blockers:
        if blocker.blocker_type != "MISSING_ROUTING":
            continue
        if blocker.valve_id is None or blocker.component_line_no is None:
            continue
        key = ComponentKey(valve_id=blocker.valve_id, component_line_no=blocker.component_line_no)
        offsets[key] = None

    return offsets
