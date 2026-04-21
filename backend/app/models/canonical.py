from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.db.base import Base


class Valve(Base):
    __tablename__ = "valves"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "valve_id", name="uq_valves_run_valve_id"),
        CheckConstraint("value_cr >= 0", name="ck_valves_value_cr_nonnegative"),
        Index("ix_valves_run_assembly_date", "planning_run_id", "assembly_date"),
        Index("ix_valves_run_dispatch_date", "planning_run_id", "dispatch_date"),
        Index("ix_valves_run_customer", "planning_run_id", "customer"),
        Index("ix_valves_run_priority", "planning_run_id", "priority"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    valve_id: Mapped[str] = mapped_column(String, nullable=False)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    customer: Mapped[str] = mapped_column(String, nullable=False)
    valve_type: Mapped[str | None] = mapped_column(String, nullable=True)
    dispatch_date: Mapped[str] = mapped_column(String, nullable=False)
    assembly_date: Mapped[str] = mapped_column(String, nullable=False)
    value_cr: Mapped[float] = mapped_column(nullable=False)
    priority: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String, nullable=True)


class ComponentStatus(Base):
    __tablename__ = "component_statuses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["planning_run_id", "valve_id"],
            ["valves.planning_run_id", "valves.valve_id"],
            name="fk_component_statuses_run_valve",
        ),
        UniqueConstraint(
            "planning_run_id",
            "valve_id",
            "component_line_no",
            name="uq_component_statuses_run_valve_line",
        ),
        CheckConstraint("qty > 0", name="ck_component_statuses_qty_positive"),
        CheckConstraint("fabrication_required in (0, 1)", name="ck_component_statuses_fabrication_required_bool"),
        CheckConstraint("fabrication_complete in (0, 1)", name="ck_component_statuses_fabrication_complete_bool"),
        CheckConstraint("critical in (0, 1)", name="ck_component_statuses_critical_bool"),
        CheckConstraint("priority_eligible is null or priority_eligible in (0, 1)", name="ck_component_statuses_priority_eligible_bool"),
        CheckConstraint(
            "ready_date_type in ('CONFIRMED', 'EXPECTED', 'TENTATIVE')",
            name="ck_component_statuses_ready_date_type",
        ),
        Index("ix_component_statuses_run_valve", "planning_run_id", "valve_id"),
        Index("ix_component_statuses_run_component", "planning_run_id", "component"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    valve_id: Mapped[str] = mapped_column(String, nullable=False)
    component_line_no: Mapped[int] = mapped_column(nullable=False)
    component: Mapped[str] = mapped_column(String, nullable=False)
    qty: Mapped[float] = mapped_column(nullable=False)
    fabrication_required: Mapped[int] = mapped_column(nullable=False)
    fabrication_complete: Mapped[int] = mapped_column(nullable=False)
    expected_ready_date: Mapped[str] = mapped_column(String, nullable=False)
    critical: Mapped[int] = mapped_column(nullable=False)
    expected_from_fabrication: Mapped[str | None] = mapped_column(String, nullable=True)
    priority_eligible: Mapped[int | None] = mapped_column(nullable=True)
    ready_date_type: Mapped[str] = mapped_column(String, nullable=False)
    current_location: Mapped[str | None] = mapped_column(String, nullable=True)
    comments: Mapped[str | None] = mapped_column(String, nullable=True)


class RoutingOperation(Base):
    __tablename__ = "routing_operations"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "component", "operation_no", name="uq_routing_operations_run_component_operation"),
        CheckConstraint("operation_no > 0", name="ck_routing_operations_operation_no_positive"),
        CheckConstraint("std_setup_hrs is null or std_setup_hrs >= 0", name="ck_routing_operations_setup_nonnegative"),
        CheckConstraint("std_run_hrs is null or std_run_hrs >= 0", name="ck_routing_operations_run_nonnegative"),
        CheckConstraint("std_total_hrs > 0", name="ck_routing_operations_total_positive"),
        CheckConstraint("subcontract_allowed in (0, 1)", name="ck_routing_operations_subcontract_allowed_bool"),
        Index("ix_routing_operations_run_component", "planning_run_id", "component"),
        Index("ix_routing_operations_run_machine_type", "planning_run_id", "machine_type"),
        Index("ix_routing_operations_run_vendor_process", "planning_run_id", "vendor_process"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    component: Mapped[str] = mapped_column(String, nullable=False)
    operation_no: Mapped[int] = mapped_column(nullable=False)
    operation_name: Mapped[str] = mapped_column(String, nullable=False)
    machine_type: Mapped[str] = mapped_column(String, nullable=False)
    alt_machine: Mapped[str | None] = mapped_column(String, nullable=True)
    std_setup_hrs: Mapped[float | None] = mapped_column(nullable=True)
    std_run_hrs: Mapped[float | None] = mapped_column(nullable=True)
    std_total_hrs: Mapped[float] = mapped_column(nullable=False)
    subcontract_allowed: Mapped[int] = mapped_column(nullable=False)
    vendor_process: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)


class Machine(Base):
    __tablename__ = "machines"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "machine_id", name="uq_machines_run_machine_id"),
        CheckConstraint("hours_per_day > 0", name="ck_machines_hours_per_day_positive"),
        CheckConstraint("efficiency_percent > 0 and efficiency_percent <= 100", name="ck_machines_efficiency_range"),
        CheckConstraint("effective_hours_day > 0", name="ck_machines_effective_hours_day_positive"),
        CheckConstraint("buffer_days > 0", name="ck_machines_buffer_days_positive"),
        CheckConstraint("active in (0, 1)", name="ck_machines_active_bool"),
        Index("ix_machines_run_machine_type", "planning_run_id", "machine_type"),
        Index("ix_machines_run_active", "planning_run_id", "active"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    machine_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    hours_per_day: Mapped[float] = mapped_column(nullable=False)
    efficiency_percent: Mapped[float] = mapped_column(nullable=False)
    effective_hours_day: Mapped[float] = mapped_column(nullable=False)
    shift_pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    buffer_days: Mapped[float] = mapped_column(nullable=False)
    capability_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[int] = mapped_column(nullable=False)


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("planning_run_id", "vendor_id", name="uq_vendors_run_vendor_id"),
        CheckConstraint("turnaround_days >= 0", name="ck_vendors_turnaround_nonnegative"),
        CheckConstraint("transport_days_total >= 0", name="ck_vendors_transport_nonnegative"),
        CheckConstraint("effective_lead_days >= 0", name="ck_vendors_effective_lead_nonnegative"),
        CheckConstraint("approved in (0, 1)", name="ck_vendors_approved_bool"),
        Index("ix_vendors_run_primary_process", "planning_run_id", "primary_process"),
        Index("ix_vendors_run_approved", "planning_run_id", "approved"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    planning_run_id: Mapped[str] = mapped_column(ForeignKey("planning_runs.id"), nullable=False)
    vendor_id: Mapped[str] = mapped_column(String, nullable=False)
    vendor_name: Mapped[str] = mapped_column(String, nullable=False)
    primary_process: Mapped[str] = mapped_column(String, nullable=False)
    turnaround_days: Mapped[float] = mapped_column(nullable=False)
    transport_days_total: Mapped[float] = mapped_column(nullable=False)
    effective_lead_days: Mapped[float] = mapped_column(nullable=False)
    capacity_rating: Mapped[str | None] = mapped_column(String, nullable=True)
    reliability: Mapped[str | None] = mapped_column(String, nullable=True)
    approved: Mapped[int] = mapped_column(nullable=False)
    comments: Mapped[str | None] = mapped_column(String, nullable=True)
