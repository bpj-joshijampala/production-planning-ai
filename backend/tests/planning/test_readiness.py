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
from app.planning.readiness import (
    ComponentKey,
    calculate_component_readiness,
    calculate_valve_readiness,
)


def test_calculate_component_and_valve_readiness_for_full_kit_ready_valve() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 4, 26)),
        ),
        component_statuses=(
            _component("V-100", 1, "Body", fabrication_required=False, fabrication_complete=True, expected_ready_date=date(2026, 4, 21)),
            _component("V-100", 2, "Bonnet", fabrication_required=True, fabrication_complete=True, expected_ready_date=date(2026, 4, 22)),
        ),
        routing_operations=(
            _routing("Body", 10),
            _routing("Bonnet", 10),
        ),
    )

    component_readiness = calculate_component_readiness(
        planning_input,
        component_completion_offsets={
            ComponentKey(valve_id="V-100", component_line_no=1): 0.0,
            ComponentKey(valve_id="V-100", component_line_no=2): 1.0,
        },
    )
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)

    assert [row.current_ready_flag for row in component_readiness] == [True, True]
    assert [row.planned_component_flag for row in component_readiness] == [True, True]
    assert valve_readiness[0].total_components == 2
    assert valve_readiness[0].ready_components == 2
    assert valve_readiness[0].required_components == 2
    assert valve_readiness[0].ready_required_count == 2
    assert valve_readiness[0].pending_required_count == 0
    assert valve_readiness[0].full_kit_flag is True
    assert valve_readiness[0].near_ready_flag is False
    assert valve_readiness[0].valve_expected_completion_date == date(2026, 4, 22)
    assert valve_readiness[0].otd_delay_days == pytest.approx(0.0)
    assert valve_readiness[0].otd_risk_flag is False
    assert valve_readiness[0].readiness_status == "READY"
    assert valve_readiness[0].risk_reason is None


def test_calculate_valve_readiness_marks_near_ready_when_one_required_component_is_pending() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 4, 25)),
        ),
        component_statuses=(
            _component("V-100", 1, "Body", expected_ready_date=date(2026, 4, 21)),
            _component("V-100", 2, "Bonnet", expected_ready_date=date(2026, 4, 22)),
            _component(
                "V-100",
                3,
                "Gate",
                fabrication_required=True,
                fabrication_complete=False,
                expected_ready_date=date(2026, 4, 23),
            ),
        ),
        routing_operations=(
            _routing("Body", 10),
            _routing("Bonnet", 10),
            _routing("Gate", 10),
        ),
    )

    valve_readiness = calculate_valve_readiness(
        planning_input,
        calculate_component_readiness(
            planning_input,
            component_completion_offsets={
                ComponentKey(valve_id="V-100", component_line_no=1): 0.0,
                ComponentKey(valve_id="V-100", component_line_no=2): 1.0,
                ComponentKey(valve_id="V-100", component_line_no=3): 2.0,
            },
        ),
    )

    assert valve_readiness[0].required_components == 3
    assert valve_readiness[0].ready_required_count == 2
    assert valve_readiness[0].pending_required_count == 1
    assert valve_readiness[0].full_kit_flag is False
    assert valve_readiness[0].near_ready_flag is True
    assert valve_readiness[0].readiness_status == "NEAR_READY"
    assert valve_readiness[0].risk_reason == "Missing component"


def test_calculate_valve_readiness_marks_at_risk_when_expected_completion_exceeds_assembly_date() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100", assembly_date=date(2026, 4, 24)),
        ),
        component_statuses=(
            _component(
                "V-100",
                1,
                "Body",
                fabrication_required=True,
                fabrication_complete=False,
                expected_ready_date=date(2026, 4, 29),
            ),
        ),
        routing_operations=(
            _routing("Body", 10),
        ),
    )

    valve_readiness = calculate_valve_readiness(
        planning_input,
        calculate_component_readiness(
            planning_input,
            component_completion_offsets={
                ComponentKey(valve_id="V-100", component_line_no=1): 8.0,
            },
        ),
    )

    assert valve_readiness[0].valve_expected_completion_date == date(2026, 4, 29)
    assert valve_readiness[0].otd_delay_days == pytest.approx(5.0)
    assert valve_readiness[0].otd_risk_flag is True
    assert valve_readiness[0].readiness_status == "AT_RISK"
    assert valve_readiness[0].risk_reason == "Missing component"


def test_calculate_valve_readiness_falls_back_to_all_components_when_no_critical_components_exist() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100"),
        ),
        component_statuses=(
            _component("V-100", 1, "Body", critical=False, expected_ready_date=date(2026, 4, 21)),
            _component("V-100", 2, "Bonnet", critical=False, expected_ready_date=date(2026, 4, 22)),
        ),
        routing_operations=(
            _routing("Body", 10),
            _routing("Bonnet", 10),
        ),
    )

    valve_readiness = calculate_valve_readiness(
        planning_input,
        calculate_component_readiness(
            planning_input,
            component_completion_offsets={
                ComponentKey(valve_id="V-100", component_line_no=1): 0.0,
                ComponentKey(valve_id="V-100", component_line_no=2): 1.0,
            },
        ),
    )

    assert valve_readiness[0].required_components == 2
    assert valve_readiness[0].full_kit_flag is True


def test_calculate_valve_readiness_marks_data_incomplete_when_required_component_has_no_completion_offset() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100"),
        ),
        component_statuses=(
            _component("V-100", 1, "Body", expected_ready_date=date(2026, 4, 21)),
        ),
        routing_operations=(
            _routing("Body", 10),
        ),
    )

    component_readiness = calculate_component_readiness(
        planning_input,
        component_completion_offsets={
            ComponentKey(valve_id="V-100", component_line_no=1): None,
        },
    )
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)

    assert valve_readiness[0].valve_expected_completion_offset_days is None
    assert valve_readiness[0].valve_expected_completion_date is None
    assert valve_readiness[0].otd_delay_days == pytest.approx(0.0)
    assert valve_readiness[0].otd_risk_flag is False
    assert valve_readiness[0].readiness_status == "DATA_INCOMPLETE"
    assert valve_readiness[0].risk_reason == "Data issue"


def test_calculate_component_readiness_marks_routed_component_incomplete_without_completion_offsets() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100"),
        ),
        component_statuses=(
            _component("V-100", 1, "Body", expected_ready_date=date(2026, 4, 22)),
        ),
        routing_operations=(
            _routing("Body", 10),
        ),
    )

    component_readiness = calculate_component_readiness(planning_input)
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)

    assert component_readiness[0].component_expected_completion_offset_days is None
    assert valve_readiness[0].readiness_status == "DATA_INCOMPLETE"
    assert valve_readiness[0].risk_reason == "Data issue"


def test_calculate_valve_readiness_marks_valve_without_components_as_data_incomplete() -> None:
    planning_input = _planning_input(
        valves=(
            _valve("V-100"),
        ),
        component_statuses=(),
        routing_operations=(),
    )

    valve_readiness = calculate_valve_readiness(planning_input, ())

    assert valve_readiness[0].total_components == 0
    assert valve_readiness[0].required_components == 0
    assert valve_readiness[0].full_kit_flag is False
    assert valve_readiness[0].readiness_status == "DATA_INCOMPLETE"
    assert valve_readiness[0].risk_reason == "Data issue"


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


def _valve(valve_id: str, *, assembly_date: date = date(2026, 4, 28)) -> ValveInput:
    return ValveInput(
        valve_id=valve_id,
        order_id=f"O-{valve_id}",
        customer="Acme",
        valve_type="Gate",
        dispatch_date=date(2026, 5, 1),
        assembly_date=assembly_date,
        value_cr=1.25,
        priority="A",
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
        ready_date_type="CONFIRMED" if fabrication_complete or not fabrication_required else "EXPECTED",
        current_location=None,
        comments=None,
    )


def _routing(component: str, operation_no: int) -> RoutingOperationInput:
    return RoutingOperationInput(
        component=component,
        operation_no=operation_no,
        operation_name="Op",
        machine_type="HBM",
        alt_machine=None,
        std_setup_hrs=None,
        std_run_hrs=None,
        std_total_hrs=2.0,
        subcontract_allowed=False,
        vendor_process=None,
        notes=None,
    )
