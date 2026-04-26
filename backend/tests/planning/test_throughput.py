from datetime import date

import pytest

from app.planning.input_loader import build_planning_settings
from app.planning.readiness import ValveReadinessSummaryData
from app.planning.throughput import calculate_throughput_summary


def test_calculate_throughput_summary_counts_only_valves_completed_within_selected_horizon() -> None:
    settings = build_planning_settings(planning_start_date=date(2026, 4, 21), planning_horizon_days=7)

    summary = calculate_throughput_summary(
        settings=settings,
        valve_readiness=(
            _valve_summary("V-100", value_cr=1.25, completion_date=date(2026, 4, 23)),
            _valve_summary("V-200", value_cr=0.50, completion_date=date(2026, 4, 28)),
            _valve_summary("V-300", value_cr=0.75, completion_date=date(2026, 4, 29)),
            _valve_summary("V-400", value_cr=0.20, completion_date=date(2026, 4, 20)),
            _valve_summary("V-500", value_cr=0.80, completion_date=None, readiness_status="DATA_INCOMPLETE"),
        ),
    )

    assert summary.target_throughput_value_cr == pytest.approx(2.5)
    assert summary.planned_throughput_value_cr == pytest.approx(1.75)
    assert summary.throughput_gap_cr == pytest.approx(0.75)
    assert summary.throughput_risk_flag is True


def test_calculate_throughput_summary_scales_target_for_fourteen_day_horizon() -> None:
    settings = build_planning_settings(planning_start_date=date(2026, 4, 21), planning_horizon_days=14)

    summary = calculate_throughput_summary(
        settings=settings,
        valve_readiness=(
            _valve_summary("V-100", value_cr=2.50, completion_date=date(2026, 4, 25)),
            _valve_summary("V-200", value_cr=2.60, completion_date=date(2026, 5, 5)),
        ),
    )

    assert summary.target_throughput_value_cr == pytest.approx(5.0)
    assert summary.planned_throughput_value_cr == pytest.approx(5.1)
    assert summary.throughput_gap_cr == pytest.approx(0.0)
    assert summary.throughput_risk_flag is False


def _valve_summary(
    valve_id: str,
    *,
    value_cr: float,
    completion_date: date | None,
    readiness_status: str = "READY",
) -> ValveReadinessSummaryData:
    return ValveReadinessSummaryData(
        valve_id=valve_id,
        customer="Customer",
        assembly_date=date(2026, 4, 28),
        dispatch_date=date(2026, 5, 1),
        value_cr=value_cr,
        total_components=1,
        ready_components=1,
        required_components=1,
        ready_required_count=1,
        pending_required_count=0,
        full_kit_flag=True,
        near_ready_flag=False,
        valve_expected_completion_offset_days=None,
        valve_expected_completion_date=completion_date,
        otd_delay_days=0.0,
        otd_risk_flag=False,
        readiness_status=readiness_status,
        risk_reason=None,
        valve_flow_gap_days=None,
        valve_flow_imbalance_flag=False,
    )
