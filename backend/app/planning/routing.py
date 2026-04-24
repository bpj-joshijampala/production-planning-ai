from dataclasses import dataclass
from datetime import date

from app.planning.input_loader import PlanningInput, RoutingOperationInput
from app.planning.priority import PrioritizedComponentData


class RoutingExpansionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PlannedOperationData:
    valve_id: str
    component_line_no: int
    component: str
    operation_no: int
    operation_name: str
    machine_type: str
    alt_machine: str | None
    qty: float
    operation_hours: float
    availability_date: date
    date_confidence: str
    priority_score: float
    sort_sequence: int
    assembly_date: date
    dispatch_date: date
    value_cr: float
    availability_offset_days: float
    operation_arrival_offset_days: float | None
    operation_arrival_date: date | None
    scheduled_start_offset_days: float | None
    internal_wait_days: float | None
    processing_time_days: float | None
    internal_completion_days: float | None
    internal_completion_offset_days: float | None
    internal_completion_date: date | None
    extreme_delay_flag: bool | None
    recommendation_status: str | None


@dataclass(frozen=True, slots=True)
class FlowBlockerData:
    planned_operation_id: str | None
    valve_id: str | None
    component_line_no: int | None
    component: str | None
    operation_name: str | None
    blocker_type: str
    cause: str
    recommended_action: str
    severity: str


@dataclass(frozen=True, slots=True)
class RoutingExpansionResult:
    planned_operations: tuple[PlannedOperationData, ...]
    flow_blockers: tuple[FlowBlockerData, ...]


def expand_routing_operations(
    *,
    planning_input: PlanningInput,
    prioritized_components: tuple[PrioritizedComponentData, ...],
) -> RoutingExpansionResult:
    routing_by_component = _routing_by_component(planning_input.routing_operations)
    planned_operations: list[PlannedOperationData] = []
    flow_blockers: list[FlowBlockerData] = []
    sort_sequence = 1

    for component_row in prioritized_components:
        routing_rows = routing_by_component.get(component_row.component, ())
        if not routing_rows:
            flow_blockers.append(
                FlowBlockerData(
                    planned_operation_id=None,
                    valve_id=component_row.valve_id,
                    component_line_no=component_row.component_line_no,
                    component=component_row.component,
                    operation_name=None,
                    blocker_type="MISSING_ROUTING",
                    cause="Component requires machining but Routing_Master has no matching row.",
                    recommended_action="Add routing for component before planning.",
                    severity="CRITICAL",
                )
            )
            continue

        availability_offset_days = float(
            max(0, (component_row.availability_date - planning_input.settings.planning_start_date).days)
        )

        for routing_row in routing_rows:
            planned_operations.append(
                PlannedOperationData(
                    valve_id=component_row.valve_id,
                    component_line_no=component_row.component_line_no,
                    component=component_row.component,
                    operation_no=routing_row.operation_no,
                    operation_name=routing_row.operation_name,
                    machine_type=routing_row.machine_type,
                    alt_machine=routing_row.alt_machine,
                    qty=component_row.qty,
                    operation_hours=component_row.qty * _std_total_hours(routing_row),
                    availability_date=component_row.availability_date,
                    date_confidence=component_row.date_confidence,
                    priority_score=component_row.priority_score,
                    sort_sequence=sort_sequence,
                    assembly_date=component_row.assembly_date,
                    dispatch_date=component_row.dispatch_date,
                    value_cr=component_row.value_cr,
                    availability_offset_days=availability_offset_days,
                    operation_arrival_offset_days=None,
                    operation_arrival_date=None,
                    scheduled_start_offset_days=None,
                    internal_wait_days=None,
                    processing_time_days=None,
                    internal_completion_days=None,
                    internal_completion_offset_days=None,
                    internal_completion_date=None,
                    extreme_delay_flag=None,
                    recommendation_status=None,
                )
            )
            sort_sequence += 1

    return RoutingExpansionResult(
        planned_operations=tuple(planned_operations),
        flow_blockers=tuple(flow_blockers),
    )


def _routing_by_component(
    routing_operations: tuple[RoutingOperationInput, ...],
) -> dict[str, tuple[RoutingOperationInput, ...]]:
    grouped: dict[str, list[RoutingOperationInput]] = {}
    for row in routing_operations:
        grouped.setdefault(row.component, []).append(row)

    return {
        component: tuple(sorted(rows, key=lambda row: row.operation_no))
        for component, rows in grouped.items()
    }


def _std_total_hours(routing_row: RoutingOperationInput) -> float:
    if routing_row.std_total_hrs > 0:
        return routing_row.std_total_hrs
    if routing_row.std_setup_hrs is not None and routing_row.std_run_hrs is not None:
        total = routing_row.std_setup_hrs + routing_row.std_run_hrs
        if total > 0:
            return total
    raise RoutingExpansionError(
        "INVALID_ROUTING_HOURS",
        (
            f"Component {routing_row.component} operation {routing_row.operation_no} "
            "has no valid standard hours for routing expansion."
        ),
    )
