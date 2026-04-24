from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

from app.planning.input_loader import ComponentStatusInput, PlanningInput


@dataclass(frozen=True, slots=True)
class ComponentKey:
    valve_id: str
    component_line_no: int


@dataclass(frozen=True, slots=True)
class ComponentReadiness:
    valve_id: str
    component_line_no: int
    component: str
    current_ready_flag: bool
    availability_date: date
    availability_offset_days: float
    in_horizon_flag: bool
    planned_component_flag: bool
    required_for_assembly_flag: bool
    component_expected_completion_offset_days: float | None


@dataclass(frozen=True, slots=True)
class ValveReadinessSummaryData:
    valve_id: str
    customer: str
    assembly_date: date
    dispatch_date: date
    value_cr: float
    total_components: int
    ready_components: int
    required_components: int
    ready_required_count: int
    pending_required_count: int
    full_kit_flag: bool
    near_ready_flag: bool
    valve_expected_completion_offset_days: float | None
    valve_expected_completion_date: date | None
    otd_delay_days: float
    otd_risk_flag: bool
    readiness_status: str
    risk_reason: str | None
    valve_flow_gap_days: float | None
    valve_flow_imbalance_flag: bool


def calculate_component_readiness(
    planning_input: PlanningInput,
    *,
    component_completion_offsets: dict[ComponentKey, float | None] | None = None,
) -> tuple[ComponentReadiness, ...]:
    required_component_keys = _required_component_keys_by_valve(planning_input.component_statuses)
    routing_components = {row.component for row in planning_input.routing_operations}

    readiness_rows: list[ComponentReadiness] = []
    for component in planning_input.component_statuses:
        current_ready_flag = (not component.fabrication_required) or component.fabrication_complete
        availability_date = _availability_date(component, planning_input.settings.planning_start_date)
        availability_offset_days = float(max(0, (availability_date - planning_input.settings.planning_start_date).days))
        in_horizon_flag = (
            availability_date >= planning_input.settings.planning_start_date
            and availability_date <= planning_input.settings.planning_end_date
        )
        planned_component_flag = current_ready_flag or in_horizon_flag
        key = ComponentKey(valve_id=component.valve_id, component_line_no=component.component_line_no)

        readiness_rows.append(
            ComponentReadiness(
                valve_id=component.valve_id,
                component_line_no=component.component_line_no,
                component=component.component,
                current_ready_flag=current_ready_flag,
                availability_date=availability_date,
                availability_offset_days=availability_offset_days,
                in_horizon_flag=in_horizon_flag,
                planned_component_flag=planned_component_flag,
                required_for_assembly_flag=key in required_component_keys[component.valve_id],
                component_expected_completion_offset_days=_component_completion_offset_days(
                    key=key,
                    availability_offset_days=availability_offset_days,
                    has_routing=component.component in routing_components,
                    component_completion_offsets=component_completion_offsets,
                ),
            )
        )

    return tuple(readiness_rows)


def calculate_valve_readiness(
    planning_input: PlanningInput,
    component_readiness: tuple[ComponentReadiness, ...],
) -> tuple[ValveReadinessSummaryData, ...]:
    readiness_by_valve: dict[str, list[ComponentReadiness]] = defaultdict(list)
    for row in component_readiness:
        readiness_by_valve[row.valve_id].append(row)

    results: list[ValveReadinessSummaryData] = []
    for valve in planning_input.valves:
        valve_components = readiness_by_valve[valve.valve_id]
        total_components = len(valve_components)
        required_components = [row for row in valve_components if row.required_for_assembly_flag]
        required_count = len(required_components)
        ready_components = sum(1 for row in valve_components if row.current_ready_flag)
        ready_required_count = sum(1 for row in required_components if row.current_ready_flag)
        pending_required_count = required_count - ready_required_count

        if total_components == 0 or required_count == 0:
            results.append(
                ValveReadinessSummaryData(
                    valve_id=valve.valve_id,
                    customer=valve.customer,
                    assembly_date=valve.assembly_date,
                    dispatch_date=valve.dispatch_date,
                    value_cr=valve.value_cr,
                    total_components=total_components,
                    ready_components=ready_components,
                    required_components=required_count,
                    ready_required_count=ready_required_count,
                    pending_required_count=max(pending_required_count, 0),
                    full_kit_flag=False,
                    near_ready_flag=False,
                    valve_expected_completion_offset_days=None,
                    valve_expected_completion_date=None,
                    otd_delay_days=0.0,
                    otd_risk_flag=False,
                    readiness_status="DATA_INCOMPLETE",
                    risk_reason="Data issue",
                    valve_flow_gap_days=None,
                    valve_flow_imbalance_flag=False,
                )
            )
            continue

        completion_offsets = [row.component_expected_completion_offset_days for row in required_components]
        completion_incomplete = any(offset is None for offset in completion_offsets)

        valve_expected_completion_offset_days = None if completion_incomplete else max(completion_offsets, default=0.0)
        valve_expected_completion_date = (
            None
            if valve_expected_completion_offset_days is None
            else planning_input.settings.planning_start_date + timedelta(days=ceil(valve_expected_completion_offset_days))
        )
        otd_delay_days = (
            0.0
            if valve_expected_completion_date is None
            else float(max(0, (valve_expected_completion_date - valve.assembly_date).days))
        )
        otd_risk_flag = (
            valve_expected_completion_date is not None and valve_expected_completion_date > valve.assembly_date
        )

        full_kit_flag = pending_required_count == 0
        near_ready_flag = 1 <= pending_required_count <= 2
        readiness_status = _readiness_status(
            valve_expected_completion_date=valve_expected_completion_date,
            otd_risk_flag=otd_risk_flag,
            full_kit_flag=full_kit_flag,
            near_ready_flag=near_ready_flag,
        )

        results.append(
            ValveReadinessSummaryData(
                valve_id=valve.valve_id,
                customer=valve.customer,
                assembly_date=valve.assembly_date,
                dispatch_date=valve.dispatch_date,
                value_cr=valve.value_cr,
                total_components=total_components,
                ready_components=ready_components,
                required_components=required_count,
                ready_required_count=ready_required_count,
                pending_required_count=pending_required_count,
                full_kit_flag=full_kit_flag,
                near_ready_flag=near_ready_flag,
                valve_expected_completion_offset_days=valve_expected_completion_offset_days,
                valve_expected_completion_date=valve_expected_completion_date,
                otd_delay_days=otd_delay_days,
                otd_risk_flag=otd_risk_flag,
                readiness_status=readiness_status,
                risk_reason=_risk_reason(
                    readiness_status=readiness_status,
                    pending_required_count=pending_required_count,
                    otd_risk_flag=otd_risk_flag,
                ),
                valve_flow_gap_days=None,
                valve_flow_imbalance_flag=False,
            )
        )

    return tuple(results)


def _required_component_keys_by_valve(
    components: tuple[ComponentStatusInput, ...],
) -> dict[str, set[ComponentKey]]:
    components_by_valve: dict[str, list[ComponentStatusInput]] = defaultdict(list)
    for component in components:
        components_by_valve[component.valve_id].append(component)

    required_keys_by_valve: dict[str, set[ComponentKey]] = {}
    for valve_id, valve_components in components_by_valve.items():
        critical_components = [component for component in valve_components if component.critical]
        assembly_required_components = critical_components if critical_components else valve_components
        required_keys_by_valve[valve_id] = {
            ComponentKey(valve_id=component.valve_id, component_line_no=component.component_line_no)
            for component in assembly_required_components
        }

    return required_keys_by_valve


def _availability_date(component: ComponentStatusInput, planning_start_date: date) -> date:
    if (not component.fabrication_required) or component.fabrication_complete:
        return max(planning_start_date, component.expected_ready_date)
    return component.expected_ready_date


def _component_completion_offset_days(
    *,
    key: ComponentKey,
    availability_offset_days: float,
    has_routing: bool,
    component_completion_offsets: dict[ComponentKey, float | None] | None,
) -> float | None:
    if component_completion_offsets is None:
        return None if has_routing else availability_offset_days
    if key in component_completion_offsets:
        return component_completion_offsets[key]
    if has_routing:
        return None
    return availability_offset_days


def _readiness_status(
    *,
    valve_expected_completion_date: date | None,
    otd_risk_flag: bool,
    full_kit_flag: bool,
    near_ready_flag: bool,
) -> str:
    if valve_expected_completion_date is None:
        return "DATA_INCOMPLETE"
    if otd_risk_flag:
        return "AT_RISK"
    if full_kit_flag:
        return "READY"
    if near_ready_flag:
        return "NEAR_READY"
    return "NOT_READY"


def _risk_reason(
    *,
    readiness_status: str,
    pending_required_count: int,
    otd_risk_flag: bool,
) -> str | None:
    if readiness_status == "DATA_INCOMPLETE":
        return "Data issue"
    if pending_required_count > 0:
        return "Missing component"
    if otd_risk_flag:
        return "Assembly delay"
    return None
