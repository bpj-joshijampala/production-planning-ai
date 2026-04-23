from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.canonical import ComponentStatus, Machine, RoutingOperation, Valve, Vendor
from app.models.planning_run import PlanningRun

ALLOWED_PLANNING_HORIZONS = frozenset({7, 14})
DEFAULT_PLANNING_HORIZON_DAYS = 7
TARGET_THROUGHPUT_PER_7_DAYS_CR = 2.5


class PlanningInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PlanningSettingsOverride:
    planning_start_date: date | str | None = None
    planning_horizon_days: int | None = None


@dataclass(frozen=True, slots=True)
class PlanningSettings:
    planning_start_date: date
    planning_horizon_days: int
    planning_end_date: date
    target_throughput_per_7_days_cr: float = TARGET_THROUGHPUT_PER_7_DAYS_CR

    @property
    def target_throughput_value_cr(self) -> float:
        return self.target_throughput_per_7_days_cr * (self.planning_horizon_days / 7)


@dataclass(frozen=True, slots=True)
class ValveInput:
    valve_id: str
    order_id: str
    customer: str
    valve_type: str | None
    dispatch_date: date
    assembly_date: date
    value_cr: float
    priority: str | None
    status: str | None
    remarks: str | None


@dataclass(frozen=True, slots=True)
class ComponentStatusInput:
    valve_id: str
    component_line_no: int
    component: str
    qty: float
    fabrication_required: bool
    fabrication_complete: bool
    expected_ready_date: date
    critical: bool
    expected_from_fabrication: date | None
    priority_eligible: bool | None
    ready_date_type: str
    current_location: str | None
    comments: str | None


@dataclass(frozen=True, slots=True)
class RoutingOperationInput:
    component: str
    operation_no: int
    operation_name: str
    machine_type: str
    alt_machine: str | None
    std_setup_hrs: float | None
    std_run_hrs: float | None
    std_total_hrs: float
    subcontract_allowed: bool
    vendor_process: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class MachineInput:
    machine_id: str
    machine_type: str
    description: str | None
    hours_per_day: float
    efficiency_percent: float
    effective_hours_day: float
    shift_pattern: str | None
    buffer_days: float
    capability_notes: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class VendorInput:
    vendor_id: str
    vendor_name: str
    primary_process: str
    turnaround_days: float
    transport_days_total: float
    effective_lead_days: float
    capacity_rating: str | None
    reliability: str | None
    approved: bool
    comments: str | None


@dataclass(frozen=True, slots=True)
class PlanningInput:
    planning_run_id: str
    upload_batch_id: str
    settings: PlanningSettings
    valves: tuple[ValveInput, ...]
    component_statuses: tuple[ComponentStatusInput, ...]
    routing_operations: tuple[RoutingOperationInput, ...]
    machines: tuple[MachineInput, ...]
    vendors: tuple[VendorInput, ...]


def build_planning_settings(
    planning_start_date: date | str,
    planning_horizon_days: int | None = None,
) -> PlanningSettings:
    start_date = _parse_required_date(planning_start_date, "planning_start_date")
    horizon_days = DEFAULT_PLANNING_HORIZON_DAYS if planning_horizon_days is None else planning_horizon_days
    if horizon_days not in ALLOWED_PLANNING_HORIZONS:
        raise PlanningInputError(
            "INVALID_PLANNING_HORIZON",
            f"planning_horizon_days must be one of {sorted(ALLOWED_PLANNING_HORIZONS)}.",
        )

    return PlanningSettings(
        planning_start_date=start_date,
        planning_horizon_days=horizon_days,
        planning_end_date=start_date + timedelta(days=horizon_days),
    )


def load_planning_input(
    planning_run_id: str,
    db: Session,
    settings_override: PlanningSettingsOverride | None = None,
) -> PlanningInput:
    planning_run = db.get(PlanningRun, planning_run_id)
    if planning_run is None:
        raise PlanningInputError("PLANNING_RUN_NOT_FOUND", f"PlanningRun {planning_run_id} was not found.")

    settings = _resolve_settings(planning_run, settings_override)
    valves = tuple(_to_valve_input(row) for row in _canonical_rows(db, Valve, planning_run.id, Valve.valve_id))
    component_statuses = tuple(
        _to_component_status_input(row)
        for row in _canonical_rows(
            db,
            ComponentStatus,
            planning_run.id,
            ComponentStatus.valve_id,
            ComponentStatus.component_line_no,
        )
    )
    routing_operations = tuple(
        _to_routing_operation_input(row)
        for row in _canonical_rows(
            db,
            RoutingOperation,
            planning_run.id,
            RoutingOperation.component,
            RoutingOperation.operation_no,
        )
    )
    machines = tuple(_to_machine_input(row) for row in _canonical_rows(db, Machine, planning_run.id, Machine.machine_id))
    vendors = tuple(_to_vendor_input(row) for row in _canonical_rows(db, Vendor, planning_run.id, Vendor.vendor_id))

    _ensure_required_inputs(
        planning_run_id=planning_run.id,
        valves=valves,
        component_statuses=component_statuses,
        routing_operations=routing_operations,
        machines=machines,
        vendors=vendors,
    )

    return PlanningInput(
        planning_run_id=planning_run.id,
        upload_batch_id=planning_run.upload_batch_id,
        settings=settings,
        valves=valves,
        component_statuses=component_statuses,
        routing_operations=routing_operations,
        machines=machines,
        vendors=vendors,
    )


def _resolve_settings(
    planning_run: PlanningRun,
    settings_override: PlanningSettingsOverride | None,
) -> PlanningSettings:
    if settings_override is None:
        return build_planning_settings(
            planning_start_date=planning_run.planning_start_date,
            planning_horizon_days=planning_run.planning_horizon_days,
        )

    return build_planning_settings(
        planning_start_date=(
            planning_run.planning_start_date
            if settings_override.planning_start_date is None
            else settings_override.planning_start_date
        ),
        planning_horizon_days=(
            planning_run.planning_horizon_days
            if settings_override.planning_horizon_days is None
            else settings_override.planning_horizon_days
        ),
    )


def _canonical_rows(db: Session, model: type[Any], planning_run_id: str, *order_by: Any) -> list[Any]:
    return list(db.scalars(select(model).where(model.planning_run_id == planning_run_id).order_by(*order_by)))


def _ensure_required_inputs(planning_run_id: str, **collections: tuple[object, ...]) -> None:
    for collection_name, rows in collections.items():
        if rows:
            continue

        raise PlanningInputError(
            "PLANNING_INPUT_EMPTY",
            f"PlanningRun {planning_run_id} has no {collection_name} canonical rows.",
        )


def _to_valve_input(row: Valve) -> ValveInput:
    return ValveInput(
        valve_id=row.valve_id,
        order_id=row.order_id,
        customer=row.customer,
        valve_type=row.valve_type,
        dispatch_date=_parse_required_date(row.dispatch_date, "dispatch_date"),
        assembly_date=_parse_required_date(row.assembly_date, "assembly_date"),
        value_cr=row.value_cr,
        priority=row.priority,
        status=row.status,
        remarks=row.remarks,
    )


def _to_component_status_input(row: ComponentStatus) -> ComponentStatusInput:
    return ComponentStatusInput(
        valve_id=row.valve_id,
        component_line_no=row.component_line_no,
        component=row.component,
        qty=row.qty,
        fabrication_required=_to_bool(row.fabrication_required),
        fabrication_complete=_to_bool(row.fabrication_complete),
        expected_ready_date=_parse_required_date(row.expected_ready_date, "expected_ready_date"),
        critical=_to_bool(row.critical),
        expected_from_fabrication=_parse_optional_date(row.expected_from_fabrication, "expected_from_fabrication"),
        priority_eligible=_to_optional_bool(row.priority_eligible),
        ready_date_type=row.ready_date_type,
        current_location=row.current_location,
        comments=row.comments,
    )


def _to_routing_operation_input(row: RoutingOperation) -> RoutingOperationInput:
    return RoutingOperationInput(
        component=row.component,
        operation_no=row.operation_no,
        operation_name=row.operation_name,
        machine_type=row.machine_type,
        alt_machine=row.alt_machine,
        std_setup_hrs=row.std_setup_hrs,
        std_run_hrs=row.std_run_hrs,
        std_total_hrs=row.std_total_hrs,
        subcontract_allowed=_to_bool(row.subcontract_allowed),
        vendor_process=row.vendor_process,
        notes=row.notes,
    )


def _to_machine_input(row: Machine) -> MachineInput:
    return MachineInput(
        machine_id=row.machine_id,
        machine_type=row.machine_type,
        description=row.description,
        hours_per_day=row.hours_per_day,
        efficiency_percent=row.efficiency_percent,
        effective_hours_day=row.effective_hours_day,
        shift_pattern=row.shift_pattern,
        buffer_days=row.buffer_days,
        capability_notes=row.capability_notes,
        active=_to_bool(row.active),
    )


def _to_vendor_input(row: Vendor) -> VendorInput:
    return VendorInput(
        vendor_id=row.vendor_id,
        vendor_name=row.vendor_name,
        primary_process=row.primary_process,
        turnaround_days=row.turnaround_days,
        transport_days_total=row.transport_days_total,
        effective_lead_days=row.effective_lead_days,
        capacity_rating=row.capacity_rating,
        reliability=row.reliability,
        approved=_to_bool(row.approved),
        comments=row.comments,
    )


def _parse_required_date(value: date | str, field_name: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise PlanningInputError("INVALID_DATE", f"{field_name} must be a valid ISO date.") from exc
    raise PlanningInputError("INVALID_DATE", f"{field_name} must be a valid ISO date.")


def _parse_optional_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    return _parse_required_date(value, field_name)


def _to_bool(value: int | bool) -> bool:
    return bool(value)


def _to_optional_bool(value: int | bool | None) -> bool | None:
    if value is None:
        return None
    return _to_bool(value)
