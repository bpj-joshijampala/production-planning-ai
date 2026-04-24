from datetime import date

import pytest

from app.planning.input_loader import (
    ComponentStatusInput,
    MachineInput,
    PlanningInput,
    PlanningSettings,
    RoutingOperationInput,
    ValveInput,
    VendorInput,
)
from app.planning.priority import calculate_component_priorities
from app.planning.queue import (
    MACHINE_TYPE_QUEUE_LIMITATION_WARNING,
    simulate_queue_and_machine_load,
)
from app.planning.readiness import calculate_component_readiness, calculate_valve_readiness
from app.planning.routing import expand_routing_operations


def test_simulate_queue_calculates_wait_completion_and_underutilized_machine_summary() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 4, 22), priority="A", value_cr=1.25),
            _valve("V-200", assembly_date=date(2026, 4, 24), priority="B", value_cr=0.5),
        ),
        component_statuses=(
            _component_status("V-100", 1, "Body", availability_date=date(2026, 4, 21)),
            _component_status("V-200", 1, "Bonnet", availability_date=date(2026, 4, 21)),
        ),
        routing_operations=(
            _routing("Body", 10, machine_type="HBM", std_total_hrs=8.0),
            _routing("Body", 20, machine_type="VTL", std_total_hrs=4.0),
            _routing("Bonnet", 10, machine_type="HBM", std_total_hrs=8.0),
        ),
        machines=(
            _machine("HBM-1", "HBM", effective_hours_day=8.0, buffer_days=5.0),
            _machine("VTL-1", "VTL", effective_hours_day=8.0, buffer_days=3.0),
        ),
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

    result = simulate_queue_and_machine_load(
        planning_input=planning_input,
        planned_operations=expansion.planned_operations,
        existing_flow_blockers=expansion.flow_blockers,
    )

    assert result.queue_approximation_warning == MACHINE_TYPE_QUEUE_LIMITATION_WARNING
    blocker_types = [row.blocker_type for row in result.flow_blockers]
    assert blocker_types == ["BATCH_RISK"]

    operations = {(row.valve_id, row.component, row.operation_no): row for row in result.planned_operations}

    body_hbm = operations[("V-100", "Body", 10)]
    assert body_hbm.operation_arrival_offset_days == pytest.approx(0.0)
    assert body_hbm.operation_arrival_date == date(2026, 4, 21)
    assert body_hbm.scheduled_start_offset_days == pytest.approx(0.0)
    assert body_hbm.internal_wait_days == pytest.approx(0.0)
    assert body_hbm.processing_time_days == pytest.approx(1.0)
    assert body_hbm.internal_completion_days == pytest.approx(1.0)
    assert body_hbm.internal_completion_offset_days == pytest.approx(1.0)
    assert body_hbm.internal_completion_date == date(2026, 4, 22)
    assert body_hbm.extreme_delay_flag is False

    body_vtl = operations[("V-100", "Body", 20)]
    assert body_vtl.operation_arrival_offset_days == pytest.approx(1.0)
    assert body_vtl.operation_arrival_date == date(2026, 4, 22)
    assert body_vtl.scheduled_start_offset_days == pytest.approx(1.0)
    assert body_vtl.internal_wait_days == pytest.approx(0.0)
    assert body_vtl.processing_time_days == pytest.approx(0.5)
    assert body_vtl.internal_completion_offset_days == pytest.approx(1.5)
    assert body_vtl.internal_completion_date == date(2026, 4, 23)

    bonnet_hbm = operations[("V-200", "Bonnet", 10)]
    assert bonnet_hbm.operation_arrival_offset_days == pytest.approx(0.0)
    assert bonnet_hbm.scheduled_start_offset_days == pytest.approx(1.0)
    assert bonnet_hbm.internal_wait_days == pytest.approx(1.0)
    assert bonnet_hbm.processing_time_days == pytest.approx(1.0)
    assert bonnet_hbm.internal_completion_offset_days == pytest.approx(2.0)
    assert bonnet_hbm.internal_completion_date == date(2026, 4, 23)
    assert bonnet_hbm.extreme_delay_flag is False

    summaries = {row.machine_type: row for row in result.machine_load_summaries}
    hbm = summaries["HBM"]
    assert hbm.total_operation_hours == pytest.approx(16.0)
    assert hbm.capacity_hours_per_day == pytest.approx(8.0)
    assert hbm.load_days == pytest.approx(2.0)
    assert hbm.buffer_days == pytest.approx(5.0)
    assert hbm.overload_flag is False
    assert hbm.overload_days == pytest.approx(0.0)
    assert hbm.spare_capacity_days == pytest.approx(3.0)
    assert hbm.underutilized_flag is True
    assert hbm.batch_risk_flag is True
    assert hbm.status == "UNDERUTILIZED"

    vtl = summaries["VTL"]
    assert vtl.total_operation_hours == pytest.approx(4.0)
    assert vtl.load_days == pytest.approx(0.5)
    assert vtl.underutilized_flag is True
    assert vtl.batch_risk_flag is False
    assert vtl.status == "UNDERUTILIZED"


def test_simulate_queue_flags_missing_machine_overload_batch_risk_and_extreme_delay() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 4, 22), priority="A", value_cr=1.25),
            _valve("V-200", assembly_date=date(2026, 4, 23), priority="B", value_cr=0.8),
            _valve("V-300", assembly_date=date(2026, 4, 24), priority="C", value_cr=0.7),
            _valve("V-400", assembly_date=date(2026, 4, 25), priority="C", value_cr=0.3),
        ),
        component_statuses=(
            _component_status("V-100", 1, "Body", availability_date=date(2026, 4, 21)),
            _component_status("V-200", 1, "Bonnet", availability_date=date(2026, 4, 21)),
            _component_status("V-300", 1, "Cover", availability_date=date(2026, 4, 21)),
            _component_status("V-400", 1, "Stem", availability_date=date(2026, 4, 21)),
        ),
        routing_operations=(
            _routing("Body", 10, machine_type="HBM", std_total_hrs=8.0),
            _routing("Bonnet", 10, machine_type="HBM", std_total_hrs=8.0),
            _routing("Cover", 10, machine_type="HBM", std_total_hrs=8.0),
            _routing("Stem", 10, machine_type="Lathe", std_total_hrs=4.0),
        ),
        machines=(
            _machine("HBM-1", "HBM", effective_hours_day=8.0, buffer_days=0.5),
        ),
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

    result = simulate_queue_and_machine_load(
        planning_input=planning_input,
        planned_operations=expansion.planned_operations,
        existing_flow_blockers=expansion.flow_blockers,
    )

    operations = {(row.valve_id, row.component, row.operation_no): row for row in result.planned_operations}
    cover_hbm = operations[("V-300", "Cover", 10)]
    assert cover_hbm.internal_wait_days == pytest.approx(2.0)
    assert cover_hbm.extreme_delay_flag is True

    missing_machine_operation = operations[("V-400", "Stem", 10)]
    assert missing_machine_operation.operation_arrival_offset_days is None
    assert missing_machine_operation.scheduled_start_offset_days is None
    assert missing_machine_operation.internal_completion_date is None
    assert missing_machine_operation.extreme_delay_flag is None

    missing_machine_blockers = [row for row in result.flow_blockers if row.blocker_type == "MISSING_MACHINE"]
    assert len(missing_machine_blockers) == 1
    assert missing_machine_blockers[0].component == "Stem"
    assert "Lathe" in missing_machine_blockers[0].cause

    overload_blockers = [row for row in result.flow_blockers if row.blocker_type == "MACHINE_OVERLOAD"]
    assert len(overload_blockers) == 1
    assert "HBM" in overload_blockers[0].cause

    batch_risk_blockers = [row for row in result.flow_blockers if row.blocker_type == "BATCH_RISK"]
    assert len(batch_risk_blockers) == 1
    assert "HBM" in batch_risk_blockers[0].cause

    extreme_delay_blockers = [row for row in result.flow_blockers if row.blocker_type == "EXTREME_DELAY"]
    assert len(extreme_delay_blockers) == 1
    assert extreme_delay_blockers[0].component == "Cover"
    assert extreme_delay_blockers[0].severity == "CRITICAL"

    summaries = {row.machine_type: row for row in result.machine_load_summaries}
    hbm = summaries["HBM"]
    assert hbm.total_operation_hours == pytest.approx(24.0)
    assert hbm.load_days == pytest.approx(3.0)
    assert hbm.buffer_days == pytest.approx(0.5)
    assert hbm.overload_flag is True
    assert hbm.overload_days == pytest.approx(2.5)
    assert hbm.spare_capacity_days == pytest.approx(0.0)
    assert hbm.underutilized_flag is False
    assert hbm.batch_risk_flag is True
    assert hbm.status == "OVERLOADED"

    lathe = summaries["Lathe"]
    assert lathe.total_operation_hours == pytest.approx(0.0)
    assert lathe.capacity_hours_per_day == pytest.approx(0.0)
    assert lathe.load_days == pytest.approx(0.0)
    assert lathe.buffer_days == pytest.approx(0.0)
    assert lathe.overload_flag is False
    assert lathe.underutilized_flag is False
    assert lathe.batch_risk_flag is False
    assert lathe.status == "DATA_INCOMPLETE"


def _planning_input(
    *,
    valves: tuple[ValveInput, ...],
    component_statuses: tuple[ComponentStatusInput, ...],
    routing_operations: tuple[RoutingOperationInput, ...],
    machines: tuple[MachineInput, ...],
) -> PlanningInput:
    return PlanningInput(
        planning_run_id="run-1",
        upload_batch_id="upload-1",
        settings=PlanningSettings(
            planning_start_date=date(2026, 4, 21),
            planning_horizon_days=7,
            planning_end_date=date(2026, 4, 28),
        ),
        valves=valves,
        component_statuses=component_statuses,
        routing_operations=routing_operations,
        machines=machines,
        vendors=(
            VendorInput(
                vendor_id="VEN-1",
                vendor_name="Vendor One",
                primary_process="HBM",
                turnaround_days=3,
                transport_days_total=1,
                effective_lead_days=4,
                capacity_rating="Medium",
                reliability="A",
                approved=True,
                comments=None,
            ),
        ),
    )


def _valve(valve_id: str, *, assembly_date: date, priority: str, value_cr: float) -> ValveInput:
    return ValveInput(
        valve_id=valve_id,
        order_id=f"O-{valve_id[2:]}",
        customer=f"Customer {valve_id}",
        valve_type="Gate",
        dispatch_date=assembly_date.replace(day=assembly_date.day + 3),
        assembly_date=assembly_date,
        value_cr=value_cr,
        priority=priority,
        status="Planned",
        remarks=None,
    )


def _component_status(
    valve_id: str,
    component_line_no: int,
    component: str,
    *,
    availability_date: date,
) -> ComponentStatusInput:
    return ComponentStatusInput(
        valve_id=valve_id,
        component_line_no=component_line_no,
        component=component,
        qty=1.0,
        fabrication_required=False,
        fabrication_complete=True,
        expected_ready_date=availability_date,
        critical=True,
        expected_from_fabrication=None,
        priority_eligible=True,
        ready_date_type="CONFIRMED",
        current_location="Stores",
        comments=None,
    )


def _routing(component: str, operation_no: int, *, machine_type: str, std_total_hrs: float) -> RoutingOperationInput:
    return RoutingOperationInput(
        component=component,
        operation_no=operation_no,
        operation_name=f"{component} op {operation_no}",
        machine_type=machine_type,
        alt_machine=None,
        std_setup_hrs=None,
        std_run_hrs=None,
        std_total_hrs=std_total_hrs,
        subcontract_allowed=False,
        vendor_process=None,
        notes=None,
    )


def _machine(
    machine_id: str,
    machine_type: str,
    *,
    effective_hours_day: float,
    buffer_days: float,
) -> MachineInput:
    return MachineInput(
        machine_id=machine_id,
        machine_type=machine_type,
        description=None,
        hours_per_day=effective_hours_day,
        efficiency_percent=100.0,
        effective_hours_day=effective_hours_day,
        shift_pattern=None,
        buffer_days=buffer_days,
        capability_notes=None,
        active=True,
    )
