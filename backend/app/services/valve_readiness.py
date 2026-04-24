from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.output import ValveReadinessSummary
from app.planning.input_loader import PlanningSettingsOverride, load_planning_input
from app.planning.readiness import ComponentKey, calculate_component_readiness, calculate_valve_readiness


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

    try:
        db.execute(
            delete(ValveReadinessSummary).where(ValveReadinessSummary.planning_run_id == planning_run_id)
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
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise

    return valve_readiness
