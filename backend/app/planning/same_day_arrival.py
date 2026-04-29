from collections import defaultdict
from datetime import date


def calculate_same_day_arrival_load_days(
    *,
    arrivals: tuple[tuple[date, str, float], ...],
    capacity_hours_per_day_by_machine: dict[str, float],
) -> dict[tuple[str, str], float]:
    same_day_arrival_hours: dict[tuple[str, str], float] = defaultdict(float)
    for arrival_date, machine_type, operation_hours in arrivals:
        capacity_hours_per_day = capacity_hours_per_day_by_machine.get(machine_type)
        if capacity_hours_per_day is None or capacity_hours_per_day <= 0:
            continue
        same_day_arrival_hours[(arrival_date.isoformat(), machine_type)] += operation_hours

    return {
        key: hours / capacity_hours_per_day_by_machine[key[1]]
        for key, hours in same_day_arrival_hours.items()
    }
