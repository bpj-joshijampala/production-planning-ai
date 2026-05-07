from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.output import FlowBlocker, IncomingLoadItem, MachineLoadSummary, PlannedOperation, Recommendation, VendorLoadSummary
from app.planning.input_loader import PlanningSettingsOverride, load_planning_input
from app.planning.priority import calculate_component_priorities
from app.planning.queue import QueueSimulationResult, simulate_queue_and_machine_load
from app.planning.readiness import (
    ComponentKey,
    build_readiness_flow_blockers,
    calculate_component_readiness,
    calculate_valve_readiness,
)
from app.planning.routing import FlowBlockerData, expand_routing_operations
from app.planning.same_day_arrival import calculate_same_day_arrival_load_days
from app.services.planning_run_metadata import upsert_planning_run_metadata
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
        combined_flow_blockers = tuple(simulation.flow_blockers)

        # Downstream outputs depend on the current planned-operation set.
        db.execute(delete(Recommendation).where(Recommendation.planning_run_id == planning_run_id))
        db.execute(delete(VendorLoadSummary).where(VendorLoadSummary.planning_run_id == planning_run_id))
        db.execute(
            delete(FlowBlocker).where(
                FlowBlocker.planning_run_id == planning_run_id,
                FlowBlocker.blocker_type.in_(
                    (
                        "MISSING_ROUTING",
                        "MISSING_COMPONENT",
                        "MISSING_MACHINE",
                        "MACHINE_OVERLOAD",
                        "BATCH_RISK",
                        "FLOW_GAP",
                        "VALVE_FLOW_IMBALANCE",
                        "EXTREME_DELAY",
                        "VENDOR_UNAVAILABLE",
                        "VENDOR_OVERLOADED",
                    )
                ),
            )
        )
        db.execute(delete(PlannedOperation).where(PlannedOperation.planning_run_id == planning_run_id))
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
                    queue_approximation_warning=simulation.queue_approximation_warning,
                )
                for row in simulation.machine_load_summaries
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
        _update_incoming_load_batch_signals(
            planning_run_id=planning_run_id,
            db=db,
            simulation=simulation,
        )
        valve_readiness = calculate_and_persist_valve_readiness(
            planning_run_id=planning_run_id,
            db=db,
            settings_override=settings_override,
            component_completion_offsets=_component_completion_offsets(
                planning_input=planning_input,
                simulation=simulation,
            ),
            commit=False,
        )
        combined_flow_blockers = combined_flow_blockers + tuple(
            FlowBlockerData(
                planned_operation_id=None,
                valve_id=row.valve_id,
                component_line_no=row.component_line_no,
                component=row.component,
                operation_name=None,
                blocker_type=row.blocker_type,
                cause=row.cause,
                recommended_action=row.recommended_action,
                severity=row.severity,
            )
            for row in build_readiness_flow_blockers(
                planning_input=planning_input,
                component_readiness=component_readiness,
                valve_readiness=valve_readiness,
            )
        )
        if settings_override is not None and commit:
            upsert_planning_run_metadata(
                planning_run_id,
                db,
                planning_settings=planning_input.settings,
            )
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise

    return QueueSimulationResult(
        planned_operations=simulation.planned_operations,
        machine_load_summaries=simulation.machine_load_summaries,
        flow_blockers=combined_flow_blockers,
        queue_approximation_warning=simulation.queue_approximation_warning,
    )


def _update_incoming_load_batch_signals(
    *,
    planning_run_id: str,
    db: Session,
    simulation: QueueSimulationResult,
) -> None:
    capacity_hours_per_day_by_machine = {
        row.machine_type: row.capacity_hours_per_day
        for row in simulation.machine_load_summaries
        if row.capacity_hours_per_day > 0
    }
    same_day_load_days = calculate_same_day_arrival_load_days(
        arrivals=tuple(
            (row.operation_arrival_date, row.machine_type, row.operation_hours)
            for row in simulation.planned_operations
            if row.operation_arrival_date is not None
        ),
        capacity_hours_per_day_by_machine=capacity_hours_per_day_by_machine,
    )
    load_days_by_component: dict[ComponentKey, float] = {}

    for row in simulation.planned_operations:
        if row.operation_arrival_date is None:
            continue
        load_days = same_day_load_days.get((row.operation_arrival_date.isoformat(), row.machine_type))
        if load_days is None:
            continue
        key = ComponentKey(valve_id=row.valve_id, component_line_no=row.component_line_no)
        load_days_by_component[key] = max(load_days_by_component.get(key, 0.0), load_days)

    incoming_rows = list(
        db.scalars(select(IncomingLoadItem).where(IncomingLoadItem.planning_run_id == planning_run_id))
    )
    for incoming_row in incoming_rows:
        key = ComponentKey(
            valve_id=incoming_row.valve_id,
            component_line_no=incoming_row.component_line_no,
        )
        load_days = load_days_by_component.get(key)
        incoming_row.same_day_arrival_load_days = load_days
        incoming_row.batch_risk_flag = 1 if load_days is not None and load_days > 1.0 else 0


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
