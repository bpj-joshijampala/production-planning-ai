from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.models.canonical import ComponentStatus, Machine, RoutingOperation, Valve, Vendor
from app.models.planning_run import MasterDataVersion, PlanningRun, PlanningSnapshot
from app.planning.input_loader import PlanningSettings


def upsert_planning_run_metadata(
    planning_run_id: str,
    db: Session,
    *,
    planning_settings: PlanningSettings | None = None,
    created_at: str | None = None,
) -> PlanningSnapshot:
    planning_run = db.get(PlanningRun, planning_run_id)
    if planning_run is None:
        raise ValueError(f"PlanningRun {planning_run_id} was not found.")

    if planning_settings is not None:
        planning_run.planning_start_date = planning_settings.planning_start_date.isoformat()
        planning_run.planning_horizon_days = planning_settings.planning_horizon_days

    timestamp = created_at or utc_now_iso()
    snapshot = _upsert_planning_snapshot(planning_run=planning_run, db=db, created_at=timestamp)
    _upsert_master_data_version(planning_run_id=planning_run.id, db=db, created_at=timestamp)
    return snapshot


def _upsert_planning_snapshot(
    *,
    planning_run: PlanningRun,
    db: Session,
    created_at: str,
) -> PlanningSnapshot:
    snapshot_payload = build_planning_snapshot_payload(planning_run=planning_run, db=db)
    snapshot_json = json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    snapshot = db.scalar(select(PlanningSnapshot).where(PlanningSnapshot.planning_run_id == planning_run.id))
    if snapshot is None:
        snapshot = PlanningSnapshot(
            id=new_uuid(),
            planning_run_id=planning_run.id,
            snapshot_json=snapshot_json,
            created_at=created_at,
        )
        db.add(snapshot)
        return snapshot

    snapshot.snapshot_json = snapshot_json
    snapshot.created_at = created_at
    return snapshot


def _upsert_master_data_version(*, planning_run_id: str, db: Session, created_at: str) -> MasterDataVersion:
    routing_version_hash = _dataset_hash(
        [_routing_snapshot(row) for row in _canonical_rows(db, RoutingOperation, planning_run_id, RoutingOperation.component, RoutingOperation.operation_no)]
    )
    machine_version_hash = _dataset_hash(
        [_machine_snapshot(row) for row in _canonical_rows(db, Machine, planning_run_id, Machine.machine_id)]
    )
    vendor_version_hash = _dataset_hash(
        [_vendor_snapshot(row) for row in _canonical_rows(db, Vendor, planning_run_id, Vendor.vendor_id)]
    )

    version = db.scalar(select(MasterDataVersion).where(MasterDataVersion.planning_run_id == planning_run_id))
    if version is None:
        version = MasterDataVersion(
            id=new_uuid(),
            planning_run_id=planning_run_id,
            routing_version_hash=routing_version_hash,
            machine_version_hash=machine_version_hash,
            vendor_version_hash=vendor_version_hash,
            created_at=created_at,
        )
        db.add(version)
        return version

    version.routing_version_hash = routing_version_hash
    version.machine_version_hash = machine_version_hash
    version.vendor_version_hash = vendor_version_hash
    version.created_at = created_at
    return version


def build_planning_snapshot_payload(*, planning_run: PlanningRun, db: Session) -> dict[str, Any]:
    valves = [_valve_snapshot(row) for row in _canonical_rows(db, Valve, planning_run.id, Valve.valve_id)]
    component_statuses = [
        _component_snapshot(row)
        for row in _canonical_rows(
            db,
            ComponentStatus,
            planning_run.id,
            ComponentStatus.valve_id,
            ComponentStatus.component_line_no,
        )
    ]
    routing_operations = [
        _routing_snapshot(row)
        for row in _canonical_rows(
            db,
            RoutingOperation,
            planning_run.id,
            RoutingOperation.component,
            RoutingOperation.operation_no,
        )
    ]
    machines = [_machine_snapshot(row) for row in _canonical_rows(db, Machine, planning_run.id, Machine.machine_id)]
    vendors = [_vendor_snapshot(row) for row in _canonical_rows(db, Vendor, planning_run.id, Vendor.vendor_id)]

    canonical = {
        "valves": valves,
        "component_statuses": component_statuses,
        "routing_operations": routing_operations,
        "machines": machines,
        "vendors": vendors,
    }

    return {
        "schema_version": 1,
        "planning_run": {
            "id": planning_run.id,
            "upload_batch_id": planning_run.upload_batch_id,
            "planning_start_date": planning_run.planning_start_date,
            "planning_horizon_days": planning_run.planning_horizon_days,
            "status": planning_run.status,
            "created_by_user_id": planning_run.created_by_user_id,
            "created_at": planning_run.created_at,
        },
        "row_counts": {key: len(rows) for key, rows in canonical.items()},
        "canonical_hash": _dataset_hash(canonical),
        "canonical": canonical,
    }


def _canonical_rows(db: Session, model: type[Any], planning_run_id: str, *order_by: Any) -> list[Any]:
    return list(
        db.scalars(
            select(model)
            .where(model.planning_run_id == planning_run_id)
            .order_by(*order_by)
        )
    )


def _dataset_hash(payload: Any) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload_json.encode("utf-8")).hexdigest()


def _valve_snapshot(row: Valve) -> dict[str, Any]:
    return {
        "valve_id": row.valve_id,
        "order_id": row.order_id,
        "customer": row.customer,
        "valve_type": row.valve_type,
        "dispatch_date": row.dispatch_date,
        "assembly_date": row.assembly_date,
        "value_cr": row.value_cr,
        "priority": row.priority,
        "status": row.status,
        "remarks": row.remarks,
    }


def _component_snapshot(row: ComponentStatus) -> dict[str, Any]:
    return {
        "valve_id": row.valve_id,
        "component_line_no": row.component_line_no,
        "component": row.component,
        "qty": row.qty,
        "fabrication_required": row.fabrication_required,
        "fabrication_complete": row.fabrication_complete,
        "expected_ready_date": row.expected_ready_date,
        "critical": row.critical,
        "expected_from_fabrication": row.expected_from_fabrication,
        "priority_eligible": row.priority_eligible,
        "ready_date_type": row.ready_date_type,
        "current_location": row.current_location,
        "comments": row.comments,
    }


def _routing_snapshot(row: RoutingOperation) -> dict[str, Any]:
    return {
        "component": row.component,
        "operation_no": row.operation_no,
        "operation_name": row.operation_name,
        "machine_type": row.machine_type,
        "alt_machine": row.alt_machine,
        "std_setup_hrs": row.std_setup_hrs,
        "std_run_hrs": row.std_run_hrs,
        "std_total_hrs": row.std_total_hrs,
        "subcontract_allowed": row.subcontract_allowed,
        "vendor_process": row.vendor_process,
        "notes": row.notes,
    }


def _machine_snapshot(row: Machine) -> dict[str, Any]:
    return {
        "machine_id": row.machine_id,
        "machine_type": row.machine_type,
        "description": row.description,
        "hours_per_day": row.hours_per_day,
        "efficiency_percent": row.efficiency_percent,
        "effective_hours_day": row.effective_hours_day,
        "shift_pattern": row.shift_pattern,
        "buffer_days": row.buffer_days,
        "capability_notes": row.capability_notes,
        "active": row.active,
    }


def _vendor_snapshot(row: Vendor) -> dict[str, Any]:
    return {
        "vendor_id": row.vendor_id,
        "vendor_name": row.vendor_name,
        "primary_process": row.primary_process,
        "turnaround_days": row.turnaround_days,
        "transport_days_total": row.transport_days_total,
        "effective_lead_days": row.effective_lead_days,
        "capacity_rating": row.capacity_rating,
        "reliability": row.reliability,
        "approved": row.approved,
        "comments": row.comments,
    }
