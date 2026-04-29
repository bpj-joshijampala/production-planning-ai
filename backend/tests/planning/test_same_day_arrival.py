from datetime import date

import pytest

from app.planning.same_day_arrival import calculate_same_day_arrival_load_days


def test_calculate_same_day_arrival_load_days_aggregates_by_day_and_machine() -> None:
    load_days = calculate_same_day_arrival_load_days(
        arrivals=(
            (date(2026, 4, 21), "HBM", 8.0),
            (date(2026, 4, 21), "HBM", 4.0),
            (date(2026, 4, 21), "VTL", 4.0),
            (date(2026, 4, 22), "HBM", 8.0),
            (date(2026, 4, 21), "EDM", 2.0),
        ),
        capacity_hours_per_day_by_machine={
            "HBM": 8.0,
            "VTL": 8.0,
            "EDM": 0.0,
        },
    )

    assert load_days == {
        ("2026-04-21", "HBM"): pytest.approx(1.5),
        ("2026-04-21", "VTL"): pytest.approx(0.5),
        ("2026-04-22", "HBM"): pytest.approx(1.0),
    }
