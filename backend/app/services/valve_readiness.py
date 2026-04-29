from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.output import FlowBlocker, ValveReadinessSummary
from app.planning.input_loader import PlanningSettingsOverride, load_planning_input
from app.planning.readiness import (
    ComponentKey,
    ReadinessFlowBlockerData,
    build_readiness_flow_blockers,
    calculate_component_readiness,
    calculate_valve_readiness,
)
from app.services.planning_run_metadata import upsert_planning_run_metadata


def calculate_and_persist_valve_readiness(
    planning_run_id: str,
    db: Session,
    *,
    settings_override: PlanningSettingsOverride | None = None,
    component_completion_offsets: dict[ComponentKey, float | None] | None = None,
    commit: bool = True,
) -> tuple:
    planning_input = load_planning_input(
        planning_run_id=planning_run_id,
        db=db,
        settings_override=settings_override,
    )
    component_readiness = calculate_component_readiness(
        planning_input,
        component_completion_offsets=component_completion_offsets,
    )
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)
    readiness_flow_blockers = build_readiness_flow_blockers(
        planning_input=planning_input,
        component_readiness=component_readiness,
        valve_readiness=valve_readiness,
    )

    try:
        db.execute(
            delete(ValveReadinessSummary).where(ValveReadinessSummary.planning_run_id == planning_run_id)
        )
        db.execute(
            delete(FlowBlocker).where(
                FlowBlocker.planning_run_id == planning_run_id,
                FlowBlocker.blocker_type.in_(("MISSING_COMPONENT", "VALVE_FLOW_IMBALANCE")),
            )
        )
        db.add_all(
            [
                ValveReadinessSummary(
                    id=new_uuid(),
                    planning_run_id=planning_run_id,
                    valve_id=row.valve_id,
                    customer=row.customer,
                    assembly_date=row.assembly_date.isoformat(),
                    dispatch_date=row.dispatch_date.isoformat(),
                    value_cr=row.value_cr,
                    total_components=row.total_components,
                    ready_components=row.ready_components,
                    required_components=row.required_components,
                    ready_required_count=row.ready_required_count,
                    pending_required_count=row.pending_required_count,
                    full_kit_flag=1 if row.full_kit_flag else 0,
                    near_ready_flag=1 if row.near_ready_flag else 0,
                    valve_expected_completion_offset_days=row.valve_expected_completion_offset_days,
                    valve_expected_completion_date=(
                        None if row.valve_expected_completion_date is None else row.valve_expected_completion_date.isoformat()
                    ),
                    otd_delay_days=row.otd_delay_days,
                    otd_risk_flag=1 if row.otd_risk_flag else 0,
                    readiness_status=row.readiness_status,
                    risk_reason=row.risk_reason,
                    valve_flow_gap_days=row.valve_flow_gap_days,
                    valve_flow_imbalance_flag=1 if row.valve_flow_imbalance_flag else 0,
                )
                for row in valve_readiness
            ]
        )
        db.add_all(
            _persisted_readiness_flow_blockers(
                planning_run_id=planning_run_id,
                flow_blockers=readiness_flow_blockers,
            )
        )
        if settings_override is not None and commit:
            upsert_planning_run_metadata(
                planning_run_id,
                db,
                planning_settings=planning_input.settings,
            )
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise

    return valve_readiness


def _persisted_readiness_flow_blockers(
    *,
    planning_run_id: str,
    flow_blockers: tuple[ReadinessFlowBlockerData, ...],
) -> list[FlowBlocker]:
    return [
        FlowBlocker(
            id=new_uuid(),
            planning_run_id=planning_run_id,
            planned_operation_id=None,
            valve_id=row.valve_id,
            component_line_no=row.component_line_no,
            component=row.component,
            operation_name=None,
            blocker_type=row.blocker_type,
            cause=row.cause,
            recommended_action=row.recommended_action,
            severity=row.severity,
        )
        for row in flow_blockers
    ]
