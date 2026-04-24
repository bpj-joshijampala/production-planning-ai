from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

from app.planning.input_loader import PlanningInput
from app.planning.routing import FlowBlockerData, PlannedOperationData

MACHINE_TYPE_QUEUE_LIMITATION_WARNING = "Queue is priority-based and aggregated by machine type. Review before execution."


@dataclass(frozen=True, slots=True)
class MachineLoadSummaryData:
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


@dataclass(frozen=True, slots=True)
class QueueSimulationResult:
    planned_operations: tuple[PlannedOperationData, ...]
    machine_load_summaries: tuple[MachineLoadSummaryData, ...]
    flow_blockers: tuple[FlowBlockerData, ...]
    queue_approximation_warning: str


def simulate_queue_and_machine_load(
    *,
    planning_input: PlanningInput,
    planned_operations: tuple[PlannedOperationData, ...],
    existing_flow_blockers: tuple[FlowBlockerData, ...] = (),
) -> QueueSimulationResult:
    capacity_by_machine_type = _capacity_by_machine_type(planning_input)
    routed_operations = sorted(
        planned_operations,
        key=lambda row: (
            -row.priority_score,
            row.assembly_date,
            row.dispatch_date,
            -row.value_cr,
            row.valve_id,
            row.component,
            row.operation_no,
            row.component_line_no,
        ),
    )

    machine_available_offset_days = {machine_type: 0.0 for machine_type in capacity_by_machine_type}
    previous_completion_by_component: dict[tuple[str, int], float | None] = {}
    queue_rows: list[PlannedOperationData] = []
    flow_blockers = list(existing_flow_blockers)

    for row in routed_operations:
        machine_capacity = capacity_by_machine_type.get(row.machine_type)
        component_key = (row.valve_id, row.component_line_no)
        previous_completion_offset = previous_completion_by_component.get(component_key, row.availability_offset_days)

        if machine_capacity is None or machine_capacity.capacity_hours_per_day <= 0:
            queue_rows.append(
                PlannedOperationData(
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    operation_no=row.operation_no,
                    operation_name=row.operation_name,
                    machine_type=row.machine_type,
                    alt_machine=row.alt_machine,
                    qty=row.qty,
                    operation_hours=row.operation_hours,
                    availability_date=row.availability_date,
                    date_confidence=row.date_confidence,
                    priority_score=row.priority_score,
                    sort_sequence=row.sort_sequence,
                    assembly_date=row.assembly_date,
                    dispatch_date=row.dispatch_date,
                    value_cr=row.value_cr,
                    availability_offset_days=row.availability_offset_days,
                    operation_arrival_offset_days=None,
                    operation_arrival_date=None,
                    scheduled_start_offset_days=None,
                    internal_wait_days=None,
                    processing_time_days=None,
                    internal_completion_days=None,
                    internal_completion_offset_days=None,
                    internal_completion_date=None,
                    extreme_delay_flag=None,
                    recommendation_status=row.recommendation_status,
                )
            )
            previous_completion_by_component[component_key] = None
            flow_blockers.append(
                FlowBlockerData(
                    planned_operation_id=None,
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    operation_name=row.operation_name,
                    blocker_type="MISSING_MACHINE",
                    cause=f"Machine_Type {row.machine_type} has no active machine capacity.",
                    recommended_action="Add active machine capacity or correct Machine_Type master data before planning.",
                    severity="CRITICAL",
                )
            )
            continue

        if previous_completion_offset is None:
            queue_rows.append(
                PlannedOperationData(
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    operation_no=row.operation_no,
                    operation_name=row.operation_name,
                    machine_type=row.machine_type,
                    alt_machine=row.alt_machine,
                    qty=row.qty,
                    operation_hours=row.operation_hours,
                    availability_date=row.availability_date,
                    date_confidence=row.date_confidence,
                    priority_score=row.priority_score,
                    sort_sequence=row.sort_sequence,
                    assembly_date=row.assembly_date,
                    dispatch_date=row.dispatch_date,
                    value_cr=row.value_cr,
                    availability_offset_days=row.availability_offset_days,
                    operation_arrival_offset_days=None,
                    operation_arrival_date=None,
                    scheduled_start_offset_days=None,
                    internal_wait_days=None,
                    processing_time_days=None,
                    internal_completion_days=None,
                    internal_completion_offset_days=None,
                    internal_completion_date=None,
                    extreme_delay_flag=None,
                    recommendation_status=row.recommendation_status,
                )
            )
            previous_completion_by_component[component_key] = None
            continue

        operation_arrival_offset_days = max(row.availability_offset_days, previous_completion_offset)
        scheduled_start_offset_days = max(
            operation_arrival_offset_days,
            machine_available_offset_days[row.machine_type],
        )
        internal_wait_days = max(0.0, scheduled_start_offset_days - operation_arrival_offset_days)
        processing_time_days = row.operation_hours / machine_capacity.capacity_hours_per_day
        internal_completion_days = internal_wait_days + processing_time_days
        internal_completion_offset_days = operation_arrival_offset_days + internal_completion_days
        extreme_delay_flag = internal_wait_days > (2 * machine_capacity.buffer_days)
        if extreme_delay_flag:
            flow_blockers.append(
                FlowBlockerData(
                    planned_operation_id=None,
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    operation_name=row.operation_name,
                    blocker_type="EXTREME_DELAY",
                    cause=(
                        f"Operation wait {internal_wait_days:.2f} days exceeds 2 x buffer_days "
                        f"{(2 * machine_capacity.buffer_days):.2f} for Machine_Type {row.machine_type}."
                    ),
                    recommended_action="Escalate queue delay and review alternate machine or subcontract decision.",
                    severity="CRITICAL",
                )
            )

        queue_rows.append(
            PlannedOperationData(
                valve_id=row.valve_id,
                component_line_no=row.component_line_no,
                component=row.component,
                operation_no=row.operation_no,
                operation_name=row.operation_name,
                machine_type=row.machine_type,
                alt_machine=row.alt_machine,
                qty=row.qty,
                operation_hours=row.operation_hours,
                availability_date=row.availability_date,
                date_confidence=row.date_confidence,
                priority_score=row.priority_score,
                sort_sequence=row.sort_sequence,
                assembly_date=row.assembly_date,
                dispatch_date=row.dispatch_date,
                value_cr=row.value_cr,
                availability_offset_days=row.availability_offset_days,
                operation_arrival_offset_days=operation_arrival_offset_days,
                operation_arrival_date=_offset_to_date(planning_input.settings.planning_start_date, operation_arrival_offset_days),
                scheduled_start_offset_days=scheduled_start_offset_days,
                internal_wait_days=internal_wait_days,
                processing_time_days=processing_time_days,
                internal_completion_days=internal_completion_days,
                internal_completion_offset_days=internal_completion_offset_days,
                internal_completion_date=_offset_to_date(
                    planning_input.settings.planning_start_date,
                    internal_completion_offset_days,
                ),
                extreme_delay_flag=extreme_delay_flag,
                recommendation_status=row.recommendation_status,
            )
        )
        machine_available_offset_days[row.machine_type] = internal_completion_offset_days
        previous_completion_by_component[component_key] = internal_completion_offset_days

    same_day_arrival_load_days = _same_day_arrival_load_days(
        planned_operations=tuple(queue_rows),
        capacity_by_machine_type=capacity_by_machine_type,
    )
    summaries = _machine_load_summaries(
        machine_types=sorted({row.machine_type for row in queue_rows} | {row.machine_type for row in planning_input.machines}),
        planned_operations=tuple(queue_rows),
        capacity_by_machine_type=capacity_by_machine_type,
        same_day_arrival_load_days=same_day_arrival_load_days,
    )
    flow_blockers.extend(_machine_summary_flow_blockers(summaries))
    flow_blockers.extend(_batch_risk_flow_blockers(same_day_arrival_load_days))

    return QueueSimulationResult(
        planned_operations=tuple(sorted(queue_rows, key=lambda row: row.sort_sequence)),
        machine_load_summaries=summaries,
        flow_blockers=tuple(flow_blockers),
        queue_approximation_warning=MACHINE_TYPE_QUEUE_LIMITATION_WARNING,
    )


@dataclass(frozen=True, slots=True)
class _MachineCapacity:
    capacity_hours_per_day: float
    buffer_days: float


def _capacity_by_machine_type(planning_input: PlanningInput) -> dict[str, _MachineCapacity]:
    capacities: dict[str, float] = defaultdict(float)
    buffers: dict[str, list[float]] = defaultdict(list)

    for machine in planning_input.machines:
        if not machine.active:
            continue
        capacities[machine.machine_type] += machine.effective_hours_day
        buffers[machine.machine_type].append(machine.buffer_days)

    return {
        machine_type: _MachineCapacity(
            capacity_hours_per_day=capacity_hours_per_day,
            buffer_days=min(buffers[machine_type]),
        )
        for machine_type, capacity_hours_per_day in capacities.items()
    }


def _same_day_arrival_load_days(
    *,
    planned_operations: tuple[PlannedOperationData, ...],
    capacity_by_machine_type: dict[str, _MachineCapacity],
) -> dict[tuple[str, str], float]:
    same_day_arrival_hours: dict[tuple[str, str], float] = defaultdict(float)
    for row in planned_operations:
        if row.operation_arrival_date is None:
            continue
        machine_capacity = capacity_by_machine_type.get(row.machine_type)
        if machine_capacity is None or machine_capacity.capacity_hours_per_day <= 0:
            continue
        same_day_arrival_hours[(row.operation_arrival_date.isoformat(), row.machine_type)] += row.operation_hours

    return {
        key: hours / capacity_by_machine_type[key[1]].capacity_hours_per_day
        for key, hours in same_day_arrival_hours.items()
    }


def _machine_load_summaries(
    *,
    machine_types: list[str],
    planned_operations: tuple[PlannedOperationData, ...],
    capacity_by_machine_type: dict[str, _MachineCapacity],
    same_day_arrival_load_days: dict[tuple[str, str], float],
) -> tuple[MachineLoadSummaryData, ...]:
    summaries: list[MachineLoadSummaryData] = []

    for machine_type in machine_types:
        machine_capacity = capacity_by_machine_type.get(machine_type)
        if machine_capacity is None or machine_capacity.capacity_hours_per_day <= 0:
            summaries.append(
                MachineLoadSummaryData(
                    machine_type=machine_type,
                    total_operation_hours=0.0,
                    capacity_hours_per_day=0.0,
                    load_days=0.0,
                    buffer_days=0.0,
                    overload_flag=False,
                    overload_days=0.0,
                    spare_capacity_days=0.0,
                    underutilized_flag=False,
                    batch_risk_flag=False,
                    status="DATA_INCOMPLETE",
                )
            )
            continue

        total_operation_hours = sum(
            row.operation_hours
            for row in planned_operations
            if row.machine_type == machine_type
        )
        load_days = total_operation_hours / machine_capacity.capacity_hours_per_day
        overload_flag = load_days > machine_capacity.buffer_days
        overload_days = max(0.0, load_days - machine_capacity.buffer_days)
        spare_capacity_days = max(0.0, machine_capacity.buffer_days - load_days)
        underutilized_flag = load_days < (0.5 * machine_capacity.buffer_days)
        batch_risk_flag = any(
            load_days_for_arrival > 1.0
            for (arrival_date, summary_machine_type), load_days_for_arrival in same_day_arrival_load_days.items()
            if summary_machine_type == machine_type and arrival_date
        )

        if overload_flag:
            status = "OVERLOADED"
        elif underutilized_flag:
            status = "UNDERUTILIZED"
        else:
            status = "OK"

        summaries.append(
            MachineLoadSummaryData(
                machine_type=machine_type,
                total_operation_hours=total_operation_hours,
                capacity_hours_per_day=machine_capacity.capacity_hours_per_day,
                load_days=load_days,
                buffer_days=machine_capacity.buffer_days,
                overload_flag=overload_flag,
                overload_days=overload_days,
                spare_capacity_days=spare_capacity_days,
                underutilized_flag=underutilized_flag,
                batch_risk_flag=batch_risk_flag,
                status=status,
            )
        )

    return tuple(summaries)


def _machine_summary_flow_blockers(
    machine_load_summaries: tuple[MachineLoadSummaryData, ...],
) -> list[FlowBlockerData]:
    blockers: list[FlowBlockerData] = []
    for summary in machine_load_summaries:
        if not summary.overload_flag:
            continue
        blockers.append(
            FlowBlockerData(
                planned_operation_id=None,
                valve_id=None,
                component_line_no=None,
                component=None,
                operation_name=None,
                blocker_type="MACHINE_OVERLOAD",
                cause=(
                    f"Machine_Type {summary.machine_type} load_days {summary.load_days:.2f} "
                    f"exceeds buffer_days {summary.buffer_days:.2f}."
                ),
                recommended_action="Review alternate machine or subcontract options and rebalance queue.",
                severity="WARNING",
            )
        )
    return blockers


def _batch_risk_flow_blockers(
    same_day_arrival_load_days: dict[tuple[str, str], float],
) -> list[FlowBlockerData]:
    blockers: list[FlowBlockerData] = []
    for (arrival_date, machine_type), load_days in sorted(same_day_arrival_load_days.items()):
        if load_days <= 1.0:
            continue
        blockers.append(
            FlowBlockerData(
                planned_operation_id=None,
                valve_id=None,
                component_line_no=None,
                component=None,
                operation_name=None,
                blocker_type="BATCH_RISK",
                cause=(
                    f"Machine_Type {machine_type} has same-day arrival load {load_days:.2f} on {arrival_date}."
                ),
                recommended_action="Review batch arrival and pre-emptive load balancing.",
                severity="INFO",
            )
        )
    return blockers


def _offset_to_date(planning_start_date: date, offset_days: float) -> date:
    return planning_start_date + timedelta(days=ceil(offset_days))
