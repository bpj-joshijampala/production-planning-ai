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
from app.planning.readiness import ValveReadinessSummaryData, calculate_component_readiness, calculate_valve_readiness


def test_calculate_component_priorities_applies_formula_scores_exactly() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 4, 24), value_cr=1.25, priority="A"),
        ),
        component_statuses=(
            _component(
                "V-100",
                1,
                "Body",
                fabrication_required=False,
                fabrication_complete=True,
                expected_ready_date=date(2026, 4, 21),
                ready_date_type="CONFIRMED",
            ),
        ),
        routing_operations=(
            _routing("Body", 10, "HBM"),
            _routing("Body", 20, "HBM"),
            _routing("Body", 30, "VTL"),
        ),
    )

    component_readiness = calculate_component_readiness(planning_input)
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)

    priorities = calculate_component_priorities(
        planning_input=planning_input,
        component_readiness=component_readiness,
        valve_readiness=valve_readiness,
    )

    assert len(priorities) == 1
    assert priorities[0].priority_score == pytest.approx(1770.0)
    assert priorities[0].date_confidence == "CONFIRMED"
    assert priorities[0].machine_types == ("HBM", "VTL")
    assert priorities[0].sort_sequence == 1


def test_calculate_component_priorities_applies_waiting_age_and_starvation_uplift() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 5, 30), value_cr=0.20, priority=None),
        ),
        component_statuses=(
            _component(
                "V-100",
                1,
                "Body",
                fabrication_required=False,
                fabrication_complete=True,
                expected_ready_date=date(2026, 4, 8),
                critical=False,
                ready_date_type="CONFIRMED",
            ),
            _component(
                "V-100",
                2,
                "Bonnet",
                fabrication_required=True,
                fabrication_complete=False,
                expected_ready_date=date(2026, 4, 22),
                critical=False,
                ready_date_type="EXPECTED",
            ),
            _component(
                "V-100",
                3,
                "Gate",
                fabrication_required=True,
                fabrication_complete=False,
                expected_ready_date=date(2026, 4, 23),
                critical=False,
                ready_date_type="EXPECTED",
            ),
            _component(
                "V-100",
                4,
                "Stem",
                fabrication_required=True,
                fabrication_complete=False,
                expected_ready_date=date(2026, 4, 24),
                critical=False,
                ready_date_type="EXPECTED",
            ),
        ),
        routing_operations=(),
    )

    component_readiness = calculate_component_readiness(planning_input)
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)
    priorities = calculate_component_priorities(
        planning_input=planning_input,
        component_readiness=component_readiness,
        valve_readiness=valve_readiness,
    )

    body_priority = next(row for row in priorities if row.component == "Body")

    assert component_readiness[0].availability_date == date(2026, 4, 21)
    assert body_priority.priority_score == pytest.approx(570.0)


def test_calculate_component_priorities_excludes_not_ready_components_outside_horizon() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 4, 24), value_cr=1.00, priority="A"),
            _valve("V-200", assembly_date=date(2026, 4, 25), value_cr=0.50, priority="B"),
        ),
        component_statuses=(
            _component(
                "V-100",
                1,
                "Body",
                fabrication_required=True,
                fabrication_complete=False,
                expected_ready_date=date(2026, 4, 25),
                ready_date_type="EXPECTED",
            ),
            _component(
                "V-200",
                1,
                "Stem",
                fabrication_required=True,
                fabrication_complete=False,
                expected_ready_date=date(2026, 5, 5),
                ready_date_type="EXPECTED",
            ),
        ),
        routing_operations=(
            _routing("Body", 10, "HBM"),
            _routing("Stem", 10, "VTL"),
        ),
    )

    component_readiness = calculate_component_readiness(planning_input)
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)

    priorities = calculate_component_priorities(
        planning_input=planning_input,
        component_readiness=component_readiness,
        valve_readiness=valve_readiness,
    )

    assert [(row.valve_id, row.component) for row in priorities] == [("V-100", "Body")]


def test_calculate_component_priorities_assigns_deterministic_sort_sequence() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-300", assembly_date=date(2026, 4, 25), dispatch_date=date(2026, 5, 2), value_cr=1.00),
            _valve("V-100", assembly_date=date(2026, 4, 25), dispatch_date=date(2026, 5, 2), value_cr=1.00),
            _valve("V-200", assembly_date=date(2026, 4, 24), dispatch_date=date(2026, 5, 3), value_cr=1.00),
            _valve("V-101", assembly_date=date(2026, 4, 25), dispatch_date=date(2026, 5, 2), value_cr=1.00),
        ),
        component_statuses=(
            _component("V-300", 1, "Stem", fabrication_required=False, fabrication_complete=True, expected_ready_date=date(2026, 4, 21)),
            _component("V-100", 2, "Body", fabrication_required=False, fabrication_complete=True, expected_ready_date=date(2026, 4, 21)),
            _component("V-200", 1, "Cover", fabrication_required=False, fabrication_complete=True, expected_ready_date=date(2026, 4, 21)),
            _component("V-101", 1, "Body", fabrication_required=False, fabrication_complete=True, expected_ready_date=date(2026, 4, 21)),
        ),
        routing_operations=(),
    )

    priorities = calculate_component_priorities(
        planning_input=planning_input,
        component_readiness=calculate_component_readiness(planning_input),
        valve_readiness=(
            _valve_readiness("V-300", assembly_date=date(2026, 4, 25), dispatch_date=date(2026, 5, 2), value_cr=1.0),
            _valve_readiness("V-100", assembly_date=date(2026, 4, 25), dispatch_date=date(2026, 5, 2), value_cr=1.0),
            _valve_readiness("V-200", assembly_date=date(2026, 4, 24), dispatch_date=date(2026, 5, 3), value_cr=1.0),
            _valve_readiness("V-101", assembly_date=date(2026, 4, 25), dispatch_date=date(2026, 5, 2), value_cr=1.0),
        ),
    )

    assert [(row.sort_sequence, row.valve_id, row.component, row.component_line_no) for row in priorities] == [
        (1, "V-200", "Cover", 1),
        (2, "V-100", "Body", 2),
        (3, "V-101", "Body", 1),
        (4, "V-300", "Stem", 1),
    ]


def _planning_input(
    *,
    valves: tuple[ValveInput, ...],
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
        valves=valves,
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


def _valve(
    valve_id: str,
    *,
    assembly_date: date,
    dispatch_date: date = date(2026, 5, 1),
    value_cr: float = 1.0,
    priority: str | None = "A",
) -> ValveInput:
    return ValveInput(
        valve_id=valve_id,
        order_id=f"O-{valve_id}",
        customer="Acme",
        valve_type="Gate",
        dispatch_date=dispatch_date,
        assembly_date=assembly_date,
        value_cr=value_cr,
        priority=priority,
        status="Planned",
        remarks=None,
    )


def _component(
    valve_id: str,
    component_line_no: int,
    component: str,
    *,
    fabrication_required: bool = True,
    fabrication_complete: bool = True,
    expected_ready_date: date,
    critical: bool = True,
    ready_date_type: str | None = None,
) -> ComponentStatusInput:
    return ComponentStatusInput(
        valve_id=valve_id,
        component_line_no=component_line_no,
        component=component,
        qty=1.0,
        fabrication_required=fabrication_required,
        fabrication_complete=fabrication_complete,
        expected_ready_date=expected_ready_date,
        critical=critical,
        expected_from_fabrication=expected_ready_date if fabrication_required else None,
        priority_eligible=None,
        ready_date_type=ready_date_type or ("CONFIRMED" if fabrication_complete or not fabrication_required else "EXPECTED"),
        current_location=None,
        comments=None,
    )


def _routing(component: str, operation_no: int, machine_type: str) -> RoutingOperationInput:
    return RoutingOperationInput(
        component=component,
        operation_no=operation_no,
        operation_name=f"{machine_type} op",
        machine_type=machine_type,
        alt_machine=None,
        std_setup_hrs=None,
        std_run_hrs=None,
        std_total_hrs=2.0,
        subcontract_allowed=False,
        vendor_process=None,
        notes=None,
    )


def _valve_readiness(
    valve_id: str,
    *,
    assembly_date: date,
    dispatch_date: date,
    value_cr: float,
) -> ValveReadinessSummaryData:
    return ValveReadinessSummaryData(
        valve_id=valve_id,
        customer="Acme",
        assembly_date=assembly_date,
        dispatch_date=dispatch_date,
        value_cr=value_cr,
        total_components=1,
        ready_components=1,
        required_components=1,
        ready_required_count=1,
        pending_required_count=0,
        full_kit_flag=False,
        near_ready_flag=False,
        valve_expected_completion_offset_days=0.0,
        valve_expected_completion_date=date(2026, 4, 21),
        otd_delay_days=0.0,
        otd_risk_flag=False,
        readiness_status="NOT_READY",
        risk_reason=None,
        valve_flow_gap_days=None,
        valve_flow_imbalance_flag=False,
    )
