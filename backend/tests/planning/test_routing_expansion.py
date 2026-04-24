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
from app.planning.priority import PrioritizedComponentData
from app.planning.routing import RoutingExpansionError, expand_routing_operations


def test_expand_routing_operations_creates_planned_operations_in_operation_order() -> None:
    planning_input = _planning_input(
        component_statuses=(
            _component_status("V-100", 1, "Body", qty=2.0),
        ),
        routing_operations=(
            _routing("Body", 20, std_total_hrs=3.0, machine_type="VTL"),
            _routing("Body", 10, std_total_hrs=5.0, machine_type="HBM"),
        ),
    )

    result = expand_routing_operations(
        planning_input=planning_input,
        prioritized_components=(
            _prioritized_component("V-100", 1, "Body", qty=2.0, sort_sequence=1),
        ),
    )

    assert [row.operation_no for row in result.planned_operations] == [10, 20]
    assert [(row.valve_id, row.component_line_no, row.component) for row in result.planned_operations] == [
        ("V-100", 1, "Body"),
        ("V-100", 1, "Body"),
    ]
    assert [row.operation_hours for row in result.planned_operations] == [10.0, 6.0]
    assert [row.sort_sequence for row in result.planned_operations] == [1, 2]
    assert result.planned_operations[0].availability_offset_days == pytest.approx(1.0)
    assert result.planned_operations[0].operation_arrival_date is None
    assert result.planned_operations[0].internal_completion_date is None
    assert result.flow_blockers == ()


def test_expand_routing_operations_uses_setup_plus_run_when_total_hours_is_zero() -> None:
    planning_input = _planning_input(
        component_statuses=(
            _component_status("V-100", 1, "Body", qty=3.0),
        ),
        routing_operations=(
            _routing(
                "Body",
                10,
                std_total_hrs=0.0,
                std_setup_hrs=1.5,
                std_run_hrs=2.5,
                machine_type="HBM",
            ),
        ),
    )

    result = expand_routing_operations(
        planning_input=planning_input,
        prioritized_components=(
            _prioritized_component("V-100", 1, "Body", qty=3.0, sort_sequence=1),
        ),
    )

    assert len(result.planned_operations) == 1
    assert result.planned_operations[0].operation_hours == pytest.approx(12.0)


def test_expand_routing_operations_creates_missing_routing_blocker_and_excludes_load() -> None:
    planning_input = _planning_input(
        component_statuses=(
            _component_status("V-100", 1, "Body"),
        ),
        routing_operations=(),
    )

    result = expand_routing_operations(
        planning_input=planning_input,
        prioritized_components=(
            _prioritized_component("V-100", 1, "Body", sort_sequence=1),
        ),
    )

    assert result.planned_operations == ()
    assert len(result.flow_blockers) == 1
    assert result.flow_blockers[0].blocker_type == "MISSING_ROUTING"
    assert result.flow_blockers[0].severity == "CRITICAL"
    assert result.flow_blockers[0].recommended_action == "Add routing for component before planning."


def test_expand_routing_operations_rejects_invalid_routing_hours_without_fallback() -> None:
    planning_input = _planning_input(
        component_statuses=(
            _component_status("V-100", 1, "Body"),
        ),
        routing_operations=(
            _routing("Body", 10, std_total_hrs=0.0, std_setup_hrs=None, std_run_hrs=None, machine_type="HBM"),
        ),
    )

    with pytest.raises(RoutingExpansionError) as exc_info:
        expand_routing_operations(
            planning_input=planning_input,
            prioritized_components=(
                _prioritized_component("V-100", 1, "Body", sort_sequence=1),
            ),
        )

    assert exc_info.value.code == "INVALID_ROUTING_HOURS"


def _planning_input(
    *,
    component_statuses: tuple[ComponentStatusInput, ...],
    routing_operations: tuple[RoutingOperationInput, ...],
) -> PlanningInput:
    return PlanningInput(
        planning_run_id="run-1",
        upload_batch_id="upload-1",
        settings=PlanningSettings(
            planning_start_date=date(2026, 4, 21),
            planning_horizon_days=7,
            planning_end_date=date(2026, 4, 28),
        ),
        valves=(
            ValveInput(
                valve_id="V-100",
                order_id="O-100",
                customer="Acme",
                valve_type="Gate",
                dispatch_date=date(2026, 5, 1),
                assembly_date=date(2026, 4, 25),
                value_cr=1.25,
                priority="A",
                status="Planned",
                remarks=None,
            ),
        ),
        component_statuses=component_statuses,
        routing_operations=routing_operations,
        machines=(
            MachineInput(
                machine_id="HBM-1",
                machine_type="HBM",
                description=None,
                hours_per_day=16,
                efficiency_percent=80,
                effective_hours_day=12.8,
                shift_pattern=None,
                buffer_days=4,
                capability_notes=None,
                active=True,
            ),
        ),
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


def _component_status(valve_id: str, component_line_no: int, component: str, *, qty: float = 1.0) -> ComponentStatusInput:
    return ComponentStatusInput(
        valve_id=valve_id,
        component_line_no=component_line_no,
        component=component,
        qty=qty,
        fabrication_required=False,
        fabrication_complete=True,
        expected_ready_date=date(2026, 4, 22),
        critical=True,
        expected_from_fabrication=None,
        priority_eligible=True,
        ready_date_type="CONFIRMED",
        current_location="Stores",
        comments=None,
    )


def _prioritized_component(
    valve_id: str,
    component_line_no: int,
    component: str,
    *,
    qty: float = 1.0,
    sort_sequence: int,
) -> PrioritizedComponentData:
    return PrioritizedComponentData(
        valve_id=valve_id,
        component_line_no=component_line_no,
        component=component,
        qty=qty,
        availability_date=date(2026, 4, 22),
        date_confidence="CONFIRMED",
        current_ready_flag=True,
        machine_types=("HBM",),
        priority_score=1200.0,
        sort_sequence=sort_sequence,
        assembly_date=date(2026, 4, 25),
        dispatch_date=date(2026, 5, 1),
        value_cr=1.25,
    )


def _routing(
    component: str,
    operation_no: int,
    *,
    std_total_hrs: float,
    machine_type: str,
    std_setup_hrs: float | None = None,
    std_run_hrs: float | None = None,
) -> RoutingOperationInput:
    return RoutingOperationInput(
        component=component,
        operation_no=operation_no,
        operation_name=f"{machine_type} op",
        machine_type=machine_type,
        alt_machine=None,
        std_setup_hrs=std_setup_hrs,
        std_run_hrs=std_run_hrs,
        std_total_hrs=std_total_hrs,
        subcontract_allowed=False,
        vendor_process=None,
        notes=None,
    )
