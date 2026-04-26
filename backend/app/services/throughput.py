from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.ids import new_uuid
from app.models.output import ThroughputSummary, ValveReadinessSummary
from app.planning.input_loader import PlanningSettingsOverride, load_planning_input
from app.planning.readiness import ValveReadinessSummaryData
from app.planning.throughput import ThroughputCalculationError, ThroughputSummaryData, calculate_throughput_summary
from app.services.planning_run_metadata import upsert_planning_run_metadata


def calculate_and_persist_throughput_summary(
    planning_run_id: str,
    db: Session,
    *,
    settings_override: PlanningSettingsOverride | None = None,
    commit: bool = True,
) -> ThroughputSummaryData:
    planning_input = load_planning_input(
        planning_run_id=planning_run_id,
        db=db,
        settings_override=settings_override,
    )
    valve_readiness = _load_valve_readiness_summaries(
        planning_run_id=planning_run_id,
        db=db,
        valve_ids={row.valve_id for row in planning_input.valves},
    )
    throughput_summary = calculate_throughput_summary(
        settings=planning_input.settings,
        valve_readiness=valve_readiness,
    )

    try:
        db.execute(delete(ThroughputSummary).where(ThroughputSummary.planning_run_id == planning_run_id))
        db.add(
            ThroughputSummary(
                id=new_uuid(),
                planning_run_id=planning_run_id,
                target_throughput_value_cr=throughput_summary.target_throughput_value_cr,
                planned_throughput_value_cr=throughput_summary.planned_throughput_value_cr,
                throughput_gap_cr=throughput_summary.throughput_gap_cr,
                throughput_risk_flag=1 if throughput_summary.throughput_risk_flag else 0,
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

    return throughput_summary


def _load_valve_readiness_summaries(
    *,
    planning_run_id: str,
    db: Session,
    valve_ids: set[str],
) -> tuple[ValveReadinessSummaryData, ...]:
    readiness_rows = list(
        db.scalars(
            select(ValveReadinessSummary)
            .where(ValveReadinessSummary.planning_run_id == planning_run_id)
            .order_by(ValveReadinessSummary.valve_id.asc())
        )
    )
    readiness_by_valve_id = {row.valve_id: row for row in readiness_rows}
    missing_valve_ids = sorted(valve_ids - readiness_by_valve_id.keys())
    if missing_valve_ids:
        raise ThroughputCalculationError(
            "VALVE_READINESS_MISSING",
            (
                "Throughput summary requires persisted valve readiness for every valve in the PlanningRun. "
                f"Missing valve_ids: {', '.join(missing_valve_ids)}."
            ),
        )

    return tuple(_to_valve_readiness_summary_data(row) for row in readiness_rows)


def _to_valve_readiness_summary_data(row: ValveReadinessSummary) -> ValveReadinessSummaryData:
    return ValveReadinessSummaryData(
        valve_id=row.valve_id,
        customer=row.customer,
        assembly_date=_parse_required_date(row.assembly_date, "assembly_date"),
        dispatch_date=_parse_required_date(row.dispatch_date, "dispatch_date"),
        value_cr=row.value_cr,
        total_components=row.total_components,
        ready_components=row.ready_components,
        required_components=row.required_components,
        ready_required_count=row.ready_required_count,
        pending_required_count=row.pending_required_count,
        full_kit_flag=bool(row.full_kit_flag),
        near_ready_flag=bool(row.near_ready_flag),
        valve_expected_completion_offset_days=row.valve_expected_completion_offset_days,
        valve_expected_completion_date=_parse_optional_date(
            row.valve_expected_completion_date,
            "valve_expected_completion_date",
        ),
        otd_delay_days=row.otd_delay_days,
        otd_risk_flag=bool(row.otd_risk_flag),
        readiness_status=row.readiness_status,
        risk_reason=row.risk_reason,
        valve_flow_gap_days=row.valve_flow_gap_days,
        valve_flow_imbalance_flag=bool(row.valve_flow_imbalance_flag),
    )


def _parse_required_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ThroughputCalculationError(
            "INVALID_VALVE_READINESS_DATE",
            f"{field_name} must be a valid ISO date.",
        ) from exc


def _parse_optional_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    return _parse_required_date(value, field_name)
