from dataclasses import dataclass

from app.planning.input_loader import PlanningSettings
from app.planning.readiness import ValveReadinessSummaryData


class ThroughputCalculationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ThroughputSummaryData:
    target_throughput_value_cr: float
    planned_throughput_value_cr: float
    throughput_gap_cr: float
    throughput_risk_flag: bool


def calculate_throughput_summary(
    *,
    settings: PlanningSettings,
    valve_readiness: tuple[ValveReadinessSummaryData, ...],
) -> ThroughputSummaryData:
    planned_throughput_value_cr = sum(
        max(row.value_cr, 0.0)
        for row in valve_readiness
        if row.valve_expected_completion_date is not None
        and settings.planning_start_date <= row.valve_expected_completion_date <= settings.planning_end_date
    )
    target_throughput_value_cr = settings.target_throughput_value_cr
    throughput_gap_cr = max(0.0, target_throughput_value_cr - planned_throughput_value_cr)

    return ThroughputSummaryData(
        target_throughput_value_cr=target_throughput_value_cr,
        planned_throughput_value_cr=planned_throughput_value_cr,
        throughput_gap_cr=throughput_gap_cr,
        throughput_risk_flag=throughput_gap_cr > 0,
    )
