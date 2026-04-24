from dataclasses import dataclass
from datetime import date

from app.planning.input_loader import ComponentStatusInput, PlanningInput, RoutingOperationInput, ValveInput
from app.planning.readiness import ComponentKey, ComponentReadiness, ValveReadinessSummaryData


class PriorityCalculationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PrioritizedComponentData:
    valve_id: str
    component_line_no: int
    component: str
    qty: float
    availability_date: date
    date_confidence: str
    current_ready_flag: bool
    machine_types: tuple[str, ...]
    priority_score: float
    sort_sequence: int
    assembly_date: date
    dispatch_date: date
    value_cr: float


def calculate_component_priorities(
    *,
    planning_input: PlanningInput,
    component_readiness: tuple[ComponentReadiness, ...],
    valve_readiness: tuple[ValveReadinessSummaryData, ...],
) -> tuple[PrioritizedComponentData, ...]:
    component_rows = {
        ComponentKey(valve_id=row.valve_id, component_line_no=row.component_line_no): row
        for row in planning_input.component_statuses
    }
    valves_by_id = {row.valve_id: row for row in planning_input.valves}
    valve_readiness_by_id = {row.valve_id: row for row in valve_readiness}
    routing_by_component = _routing_by_component(planning_input.routing_operations)

    prioritized_rows: list[PrioritizedComponentData] = []
    for row in component_readiness:
        if not row.planned_component_flag:
            continue

        key = ComponentKey(valve_id=row.valve_id, component_line_no=row.component_line_no)
        component = component_rows.get(key)
        if component is None:
            raise PriorityCalculationError(
                "COMPONENT_STATUS_NOT_FOUND",
                f"Missing canonical component row for {row.valve_id} line {row.component_line_no}.",
            )

        valve = valves_by_id.get(row.valve_id)
        if valve is None:
            raise PriorityCalculationError("VALVE_NOT_FOUND", f"Missing valve row for {row.valve_id}.")

        valve_summary = valve_readiness_by_id.get(row.valve_id)
        if valve_summary is None:
            raise PriorityCalculationError(
                "VALVE_READINESS_NOT_FOUND",
                f"Missing valve readiness summary for {row.valve_id}.",
            )

        prioritized_rows.append(
            PrioritizedComponentData(
                valve_id=row.valve_id,
                component_line_no=row.component_line_no,
                component=row.component,
                qty=component.qty,
                availability_date=row.availability_date,
                date_confidence=_date_confidence(component),
                current_ready_flag=row.current_ready_flag,
                machine_types=_machine_types(routing_by_component.get(component.component, ())),
                priority_score=_priority_score(
                    planning_start_date=planning_input.settings.planning_start_date,
                    valve=valve,
                    component=component,
                    component_readiness=row,
                    valve_readiness=valve_summary,
                ),
                sort_sequence=0,
                assembly_date=valve.assembly_date,
                dispatch_date=valve.dispatch_date,
                value_cr=valve.value_cr,
            )
        )

    sorted_rows = sorted(
        prioritized_rows,
        key=lambda row: (
            -row.priority_score,
            row.assembly_date,
            row.dispatch_date,
            -row.value_cr,
            row.valve_id,
            row.component,
            row.component_line_no,
        ),
    )

    return tuple(
        PrioritizedComponentData(
            valve_id=row.valve_id,
            component_line_no=row.component_line_no,
            component=row.component,
            qty=row.qty,
            availability_date=row.availability_date,
            date_confidence=row.date_confidence,
            current_ready_flag=row.current_ready_flag,
            machine_types=row.machine_types,
            priority_score=row.priority_score,
            sort_sequence=index,
            assembly_date=row.assembly_date,
            dispatch_date=row.dispatch_date,
            value_cr=row.value_cr,
        )
        for index, row in enumerate(sorted_rows, start=1)
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


def _machine_types(routing_operations: tuple[RoutingOperationInput, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for row in routing_operations:
        if row.machine_type in seen:
            continue
        seen.add(row.machine_type)
        ordered.append(row.machine_type)
    return tuple(ordered)


def _date_confidence(component: ComponentStatusInput) -> str:
    normalized = component.ready_date_type.strip().upper()
    if normalized not in {"CONFIRMED", "EXPECTED", "TENTATIVE"}:
        raise PriorityCalculationError(
            "INVALID_DATE_CONFIDENCE",
            f"Component {component.component} has unsupported date confidence {component.ready_date_type!r}.",
        )
    return normalized


def _priority_score(
    *,
    planning_start_date: date,
    valve: ValveInput,
    component: ComponentStatusInput,
    component_readiness: ComponentReadiness,
    valve_readiness: ValveReadinessSummaryData,
) -> float:
    days_until_assembly = max(0, (valve.assembly_date - planning_start_date).days)
    assembly_urgency_score = max(0, 30 - days_until_assembly) * 10
    full_kit_bonus = 1000 if valve_readiness.full_kit_flag else 0
    near_ready_bonus = 600 if valve_readiness.near_ready_flag else 0
    critical_component_bonus = 100 if component.critical else 0
    planner_priority_score = {"A": 300, "B": 150, "C": 50}.get((valve.priority or "").strip().upper(), 0)
    waiting_age_days = max(
        0,
        (
            planning_start_date
            - _waiting_age_reference_date(component=component, component_readiness=component_readiness)
        ).days,
    )
    waiting_age_score = min(waiting_age_days, 10) * 5
    starvation_uplift = 500 if waiting_age_days >= 10 else 0
    value_score = min(max(valve.value_cr, 0.0) * 100, 100)
    date_confidence_penalty = {"CONFIRMED": 0, "EXPECTED": 25, "TENTATIVE": 75}[_date_confidence(component)]

    return float(
        full_kit_bonus
        + near_ready_bonus
        + assembly_urgency_score
        + critical_component_bonus
        + planner_priority_score
        + waiting_age_score
        + starvation_uplift
        + value_score
        - date_confidence_penalty
    )


def _waiting_age_reference_date(
    *,
    component: ComponentStatusInput,
    component_readiness: ComponentReadiness,
) -> date:
    if component_readiness.current_ready_flag:
        return min(component.expected_ready_date, component_readiness.availability_date)
    return component_readiness.availability_date
