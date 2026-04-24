import json

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.output import IncomingLoadItem
from app.planning.input_loader import PlanningSettingsOverride, load_planning_input
from app.planning.priority import calculate_component_priorities
from app.planning.readiness import calculate_component_readiness, calculate_valve_readiness


def calculate_and_persist_incoming_load(
    planning_run_id: str,
    db: Session,
    *,
    settings_override: PlanningSettingsOverride | None = None,
    commit: bool = True,
) -> tuple:
    planning_input = load_planning_input(
        planning_run_id=planning_run_id,
        db=db,
        settings_override=settings_override,
    )
    component_readiness = calculate_component_readiness(planning_input)
    valve_readiness = calculate_valve_readiness(planning_input, component_readiness)
    prioritized_components = calculate_component_priorities(
        planning_input=planning_input,
        component_readiness=component_readiness,
        valve_readiness=valve_readiness,
    )

    try:
        db.execute(delete(IncomingLoadItem).where(IncomingLoadItem.planning_run_id == planning_run_id))
        db.add_all(
            [
                IncomingLoadItem(
                    id=new_uuid(),
                    planning_run_id=planning_run_id,
                    valve_id=row.valve_id,
                    component_line_no=row.component_line_no,
                    component=row.component,
                    qty=row.qty,
                    availability_date=row.availability_date.isoformat(),
                    date_confidence=row.date_confidence,
                    current_ready_flag=1 if row.current_ready_flag else 0,
                    machine_types_json=(
                        None
                        if not row.machine_types
                        else json.dumps(list(row.machine_types), ensure_ascii=True, separators=(",", ":"))
                    ),
                    priority_score=row.priority_score,
                    sort_sequence=row.sort_sequence,
                    same_day_arrival_load_days=None,
                    batch_risk_flag=0,
                )
                for row in prioritized_components
            ]
        )
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise

    return prioritized_components
