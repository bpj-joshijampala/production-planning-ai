from datetime import date

from app.planning.recommendations import (
    MachineLoadSummarySnapshot,
    PlannedOperationSnapshot,
    VendorLoadSummaryData,
    VendorSnapshot,
    calculate_placeholder_recommendations,
    calculate_vendor_load_summaries,
)


def test_calculate_placeholder_recommendations_assigns_expected_precedence() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-data",
                "HBM",
                subcontract_allowed=True,
                internal_completion_date=None,
                operation_arrival_offset_days=None,
                internal_wait_days=None,
                processing_time_days=None,
                internal_completion_offset_days=None,
            ),
            _operation(
                "op-delay",
                "VTL",
                subcontract_allowed=False,
                extreme_delay_flag=True,
                internal_wait_days=7.0,
                processing_time_days=1.0,
                internal_completion_offset_days=8.0,
            ),
            _operation(
                "op-overload",
                "HBM",
                subcontract_allowed=False,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=2.0,
            ),
            _operation(
                "op-batch",
                "Lathe",
                subcontract_allowed=False,
                operation_hours=12.0,
                internal_wait_days=0.5,
                processing_time_days=0.5,
                internal_completion_offset_days=1.0,
            ),
            _operation(
                "op-ok",
                "Drill",
                subcontract_allowed=False,
                internal_wait_days=0.0,
                processing_time_days=0.25,
                internal_completion_offset_days=0.25,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
            _machine_summary("VTL", overload_flag=False, batch_risk_flag=False, load_days=1.0, buffer_days=3.0),
            _machine_summary("Lathe", overload_flag=False, batch_risk_flag=True, load_days=1.0, buffer_days=3.0),
            _machine_summary("Drill", overload_flag=False, batch_risk_flag=False, load_days=0.5, buffer_days=2.0),
        ),
        vendors=(),
    )

    assert [(row.planned_operation_id, row.recommendation_type) for row in recommendations] == [
        ("op-data", "DATA_ERROR"),
        ("op-delay", "EXTREME_DELAY"),
        ("op-overload", "NO_FEASIBLE_OPTION"),
        ("op-batch", "BATCH_RISK"),
        ("op-ok", "OK_INTERNAL"),
    ]
    assert recommendations[0].reason_codes == ("DATA_ERROR",)
    assert recommendations[1].reason_codes == ("EXTREME_DELAY",)
    assert recommendations[2].reason_codes == ("NO_FEASIBLE_OPTION", "SUBCONTRACT_NOT_ALLOWED")
    assert recommendations[3].reason_codes == ("BATCH_RISK",)
    assert (
        recommendations[3].explanation
        == "Machine_Type Lathe same_day_arrival_load_days 1.50 on 2026-04-21 exceeds threshold 1.00 and requires planner review."
    )
    assert recommendations[4].status == "PENDING"


def test_calculate_placeholder_recommendations_holds_non_full_kit_work_when_priority_flow_would_be_compromised() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-priority",
                "HBM",
                subcontract_allowed=False,
                operation_hours=8.0,
                internal_wait_days=0.0,
                processing_time_days=1.0,
                internal_completion_offset_days=1.0,
                full_kit_flag=True,
            ),
            _operation(
                "op-hold",
                "HBM",
                subcontract_allowed=True,
                operation_hours=4.0,
                internal_wait_days=0.5,
                processing_time_days=1.0,
                internal_completion_offset_days=1.5,
                full_kit_flag=False,
                near_ready_flag=False,
            ),
        ),
        machine_load_summaries=(
            _machine_summary(
                "HBM",
                overload_flag=False,
                batch_risk_flag=False,
                load_days=1.5,
                buffer_days=0.75,
                spare_capacity_days=0.5,
                total_operation_hours=12.0,
                capacity_hours_per_day=8.0,
            ),
        ),
        vendors=(_vendor("VEN-1", "Vendor One", "HBM", effective_lead_days=1.0),),
    )

    assert [(row.planned_operation_id, row.recommendation_type) for row in recommendations] == [
        ("op-priority", "OK_INTERNAL"),
        ("op-hold", "HOLD_FOR_PRIORITY_FLOW"),
    ]
    assert recommendations[1].reason_codes == ("HOLD_FOR_PRIORITY_FLOW",)
    assert "priority_load_days 1.00" in recommendations[1].explanation
    assert "buffer_days 0.75" in recommendations[1].explanation
    assert "Spare_capacity_days 0.50" in recommendations[1].explanation
    assert "processing_time_days 1.00" in recommendations[1].explanation


def test_calculate_placeholder_recommendations_uses_alternate_machine_when_primary_is_overloaded_and_alternate_fits() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-alt",
                "HBM",
                alt_machine="VTL",
                subcontract_allowed=True,
                operation_hours=8.0,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=2.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary(
                "HBM",
                overload_flag=True,
                batch_risk_flag=False,
                load_days=6.0,
                buffer_days=4.0,
                total_operation_hours=48.0,
                capacity_hours_per_day=8.0,
            ),
            _machine_summary(
                "VTL",
                overload_flag=False,
                batch_risk_flag=False,
                load_days=2.0,
                buffer_days=3.0,
                total_operation_hours=16.0,
                capacity_hours_per_day=8.0,
            ),
        ),
        vendors=(_vendor("VEN-1", "Vendor One", "HBM", effective_lead_days=1.0),),
    )

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type == "USE_ALTERNATE"
    assert recommendation.suggested_machine_type == "VTL"
    assert recommendation.reason_codes == ("PRIMARY_OVERLOADED", "ALTERNATE_FEASIBLE")
    assert "HBM load_days 6.00 exceeds buffer_days 4.00" in recommendation.explanation
    assert "VTL load_days after assignment 3.00 stays within buffer_days 3.00" in recommendation.explanation
    assert recommendation.recommendation_status == "USE_ALTERNATE"


def test_calculate_placeholder_recommendations_subcontracts_when_vendor_is_faster_than_internal_completion() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-subcontract",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=2.0,
                processing_time_days=1.0,
                internal_completion_offset_days=4.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary(
                "HBM",
                overload_flag=True,
                batch_risk_flag=False,
                load_days=6.0,
                buffer_days=4.0,
                total_operation_hours=48.0,
                capacity_hours_per_day=8.0,
            ),
        ),
        vendors=(
            _vendor("VEN-2", "Vendor Slow", "HBM", effective_lead_days=3.0, reliability="A", capacity_rating="High"),
            _vendor("VEN-1", "Vendor Fast", "HBM", effective_lead_days=2.0, reliability="A", capacity_rating="High"),
        ),
    )

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation.recommendation_type == "SUBCONTRACT"
    assert recommendation.suggested_vendor_id == "VEN-1"
    assert recommendation.suggested_vendor_name == "Vendor Fast"
    assert recommendation.vendor_total_days == 2.0
    assert recommendation.vendor_gain_days == 1.0
    assert recommendation.reason_codes == ("PRIMARY_OVERLOADED", "SUBCONTRACT_FEASIBLE")
    assert "Vendor Vendor Fast total_days 2.00 beats internal completion 4.00 by 1.00 days." in recommendation.explanation
    assert "External pending load and vendor timing are only partially modeled in V1." in recommendation.explanation


def test_calculate_placeholder_recommendations_flags_batch_subcontract_opportunity_when_candidate_count_is_two() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-subcontract-1",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=2.0,
                processing_time_days=1.0,
                internal_completion_offset_days=5.0,
            ),
            _operation(
                "op-subcontract-2",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=3.0,
                processing_time_days=1.0,
                internal_completion_offset_days=6.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
        ),
        vendors=(
            _vendor("VEN-1", "Vendor One", "HBM", effective_lead_days=2.0, reliability="A", capacity_rating="Medium"),
        ),
    )

    assert [
        (
            row.planned_operation_id,
            row.recommendation_type,
            row.recommendation_status,
            row.suggested_vendor_id,
            row.subcontract_batch_candidate_count,
            row.batch_subcontract_opportunity_flag,
        )
        for row in recommendations
    ] == [
        ("op-subcontract-1", "BATCH_SUBCONTRACT_OPPORTUNITY", "SUBCONTRACT", "VEN-1", 2, True),
        ("op-subcontract-2", "BATCH_SUBCONTRACT_OPPORTUNITY", "SUBCONTRACT", "VEN-1", 2, True),
    ]
    assert recommendations[0].reason_codes == (
        "PRIMARY_OVERLOADED",
        "SUBCONTRACT_FEASIBLE",
        "BATCH_SUBCONTRACT_OPPORTUNITY",
    )
    assert "Batch opportunity candidate_count 2" in recommendations[0].explanation


def test_calculate_placeholder_recommendations_falls_back_to_machine_type_when_vendor_process_is_blank() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-subcontract",
                "HBM",
                subcontract_allowed=True,
                vendor_process=None,
                operation_arrival_offset_days=1.0,
                internal_wait_days=2.0,
                processing_time_days=1.0,
                internal_completion_offset_days=4.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
        ),
        vendors=(
            _vendor("VEN-1", "Vendor One", "HBM", effective_lead_days=2.0, reliability="A", capacity_rating="High"),
        ),
    )

    assert recommendations[0].recommendation_type == "SUBCONTRACT"
    assert recommendations[0].suggested_vendor_id == "VEN-1"
    assert recommendations[0].suggested_vendor_name == "Vendor One"


def test_calculate_placeholder_recommendations_selects_vendor_by_sort_rules() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-subcontract",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=2.0,
                processing_time_days=1.0,
                internal_completion_offset_days=5.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
        ),
        vendors=(
            _vendor("VEN-3", "Vendor Three", "HBM", effective_lead_days=2.0, reliability="B", capacity_rating="High"),
            _vendor("VEN-2", "Vendor Two", "HBM", effective_lead_days=2.0, reliability="A", capacity_rating="Medium"),
            _vendor("VEN-4", "Vendor Four", "HBM", effective_lead_days=3.0, reliability="A", capacity_rating="High"),
            _vendor("VEN-1", "Vendor One", "HBM", effective_lead_days=2.0, reliability="A", capacity_rating="High"),
        ),
    )

    assert recommendations[0].recommendation_type == "SUBCONTRACT"
    assert recommendations[0].suggested_vendor_id == "VEN-1"
    assert recommendations[0].suggested_vendor_name == "Vendor One"


def test_calculate_placeholder_recommendations_uses_no_feasible_option_when_best_vendor_is_not_faster() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-overload",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=3.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
        ),
        vendors=(
            _vendor("VEN-1", "Vendor One", "HBM", effective_lead_days=2.0, reliability="A", capacity_rating="High"),
        ),
    )

    recommendation = recommendations[0]
    assert recommendation.recommendation_type == "NO_FEASIBLE_OPTION"
    assert recommendation.suggested_vendor_id == "VEN-1"
    assert recommendation.vendor_total_days == 2.0
    assert recommendation.vendor_gain_days is None
    assert recommendation.reason_codes == ("NO_FEASIBLE_OPTION", "VENDOR_NOT_FASTER")
    assert "Best approved vendor Vendor One total_days 2.00 does not beat internal completion 3.00." in recommendation.explanation


def test_calculate_placeholder_recommendations_respects_vendor_capacity_limit_across_operations() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-subcontract-1",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=3.0,
                processing_time_days=1.0,
                internal_completion_offset_days=5.0,
            ),
            _operation(
                "op-subcontract-2",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=4.0,
                processing_time_days=1.0,
                internal_completion_offset_days=6.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
        ),
        vendors=(
            _vendor("VEN-LOW", "Vendor Low", "HBM", effective_lead_days=1.0, reliability="A", capacity_rating="Low"),
        ),
    )

    assert [(row.planned_operation_id, row.recommendation_type, row.suggested_vendor_id) for row in recommendations] == [
        ("op-subcontract-1", "BATCH_SUBCONTRACT_OPPORTUNITY", "VEN-LOW"),
        ("op-subcontract-2", "NO_FEASIBLE_OPTION", "VEN-LOW"),
    ]
    assert "current-run modeled capacity limit" in recommendations[1].explanation


def test_calculate_placeholder_recommendations_keeps_batch_candidate_count_when_vendor_capacity_blocks_later_rows() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-subcontract-1",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=3.0,
                processing_time_days=1.0,
                internal_completion_offset_days=5.0,
            ),
            _operation(
                "op-subcontract-2",
                "HBM",
                subcontract_allowed=True,
                vendor_process="HBM",
                operation_arrival_offset_days=1.0,
                internal_wait_days=4.0,
                processing_time_days=1.0,
                internal_completion_offset_days=6.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
        ),
        vendors=(
            _vendor("VEN-LOW", "Vendor Low", "HBM", effective_lead_days=1.0, reliability="A", capacity_rating="Low"),
        ),
    )

    assert [
        (
            row.planned_operation_id,
            row.recommendation_type,
            row.suggested_vendor_id,
            row.subcontract_batch_candidate_count,
            row.batch_subcontract_opportunity_flag,
        )
        for row in recommendations
    ] == [
        ("op-subcontract-1", "BATCH_SUBCONTRACT_OPPORTUNITY", "VEN-LOW", 2, True),
        ("op-subcontract-2", "NO_FEASIBLE_OPTION", "VEN-LOW", 2, True),
    ]
    assert recommendations[1].reason_codes == ("NO_FEASIBLE_OPTION", "VENDOR_CAPACITY_REACHED")
    assert "Vendor Low total_days 1.00 would beat internal completion 6.00 by 4.00 days" in recommendations[1].explanation


def test_calculate_placeholder_recommendations_reports_numeric_batch_risk_for_high_same_day_arrival_pressure() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-batch-1",
                "Lathe",
                subcontract_allowed=False,
                operation_hours=12.0,
                internal_wait_days=0.5,
                processing_time_days=0.5,
                internal_completion_offset_days=1.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary("Lathe", overload_flag=False, batch_risk_flag=True, load_days=1.5, buffer_days=3.0),
        ),
        vendors=(),
    )

    assert recommendations[0].recommendation_type == "BATCH_RISK"
    assert (
        recommendations[0].explanation
        == "Machine_Type Lathe same_day_arrival_load_days 1.50 on 2026-04-21 exceeds threshold 1.00 and requires planner review."
    )


def test_calculate_placeholder_recommendations_limits_shared_alternate_capacity_across_multiple_operations() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-alt-1",
                "HBM",
                alt_machine="VTL",
                subcontract_allowed=True,
                operation_hours=8.0,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=2.0,
            ),
            _operation(
                "op-alt-2",
                "HBM",
                alt_machine="VTL",
                subcontract_allowed=False,
                operation_hours=8.0,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=2.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary(
                "HBM",
                overload_flag=True,
                batch_risk_flag=False,
                load_days=6.0,
                buffer_days=4.0,
                total_operation_hours=48.0,
                capacity_hours_per_day=8.0,
            ),
            _machine_summary(
                "VTL",
                overload_flag=False,
                batch_risk_flag=False,
                load_days=2.0,
                buffer_days=3.0,
                total_operation_hours=16.0,
                capacity_hours_per_day=8.0,
            ),
        ),
        vendors=(_vendor("VEN-1", "Vendor One", "HBM", effective_lead_days=1.0),),
    )

    assert [(row.planned_operation_id, row.recommendation_type, row.suggested_machine_type) for row in recommendations] == [
        ("op-alt-1", "USE_ALTERNATE", "VTL"),
        ("op-alt-2", "NO_FEASIBLE_OPTION", None),
    ]


def test_calculate_placeholder_recommendations_rejects_invalid_alternate_machine_paths() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation(
                "op-same-machine",
                "HBM",
                alt_machine="HBM",
                subcontract_allowed=False,
                operation_hours=8.0,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=2.0,
            ),
            _operation(
                "op-missing-alt",
                "HBM",
                alt_machine="Drill",
                subcontract_allowed=False,
                operation_hours=8.0,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=2.0,
            ),
            _operation(
                "op-zero-capacity-alt",
                "HBM",
                alt_machine="VTL",
                subcontract_allowed=False,
                operation_hours=8.0,
                internal_wait_days=1.0,
                processing_time_days=1.0,
                internal_completion_offset_days=2.0,
            ),
        ),
        machine_load_summaries=(
            _machine_summary(
                "HBM",
                overload_flag=True,
                batch_risk_flag=False,
                load_days=6.0,
                buffer_days=4.0,
                total_operation_hours=48.0,
                capacity_hours_per_day=8.0,
            ),
            _machine_summary(
                "VTL",
                overload_flag=False,
                batch_risk_flag=False,
                load_days=0.0,
                buffer_days=3.0,
                total_operation_hours=0.0,
                capacity_hours_per_day=0.0,
            ),
        ),
        vendors=(),
    )

    assert [(row.planned_operation_id, row.recommendation_type, row.suggested_machine_type) for row in recommendations] == [
        ("op-same-machine", "NO_FEASIBLE_OPTION", None),
        ("op-missing-alt", "NO_FEASIBLE_OPTION", None),
        ("op-zero-capacity-alt", "NO_FEASIBLE_OPTION", None),
    ]


def test_calculate_vendor_load_summaries_counts_subcontract_recommendations_by_vendor() -> None:
    summaries = calculate_vendor_load_summaries(
        vendors=(
            ("VEN-1", "Vendor One", "HBM", "Medium"),
            ("VEN-2", "Vendor Two", "VTL", "Low"),
            ("VEN-3", "Vendor Three", "Drill", None),
        ),
        recommendations=(
            _recommendation_type("SUBCONTRACT", suggested_vendor_id="VEN-1", suggested_vendor_name="Vendor One"),
            _recommendation_type(
                "BATCH_SUBCONTRACT_OPPORTUNITY",
                suggested_vendor_id="VEN-1",
                suggested_vendor_name="Vendor One",
            ),
            _recommendation_type("BATCH_RISK"),
        ),
    )

    assert [(row.vendor_id, row.vendor_recommended_jobs, row.max_recommended_jobs_per_horizon, row.status) for row in summaries] == [
        ("VEN-1", 2, 3, "OK"),
        ("VEN-2", 0, 1, "OK"),
        ("VEN-3", 0, 1, "OK"),
    ]
    assert all(isinstance(row, VendorLoadSummaryData) for row in summaries)


def test_calculate_vendor_load_summaries_flags_vendor_overloaded_at_capacity_limit() -> None:
    summaries = calculate_vendor_load_summaries(
        vendors=(
            ("VEN-LOW", "Vendor Low", "HBM", "Low"),
        ),
        recommendations=(
            _recommendation_type("BATCH_SUBCONTRACT_OPPORTUNITY", suggested_vendor_id="VEN-LOW"),
        ),
    )

    assert [(row.vendor_id, row.vendor_recommended_jobs, row.max_recommended_jobs_per_horizon, row.status) for row in summaries] == [
        ("VEN-LOW", 1, 1, "VENDOR_OVERLOADED"),
    ]


def _operation(
    planned_operation_id: str,
    machine_type: str,
    *,
    subcontract_allowed: bool,
    vendor_process: str | None = None,
    internal_completion_date: str | None = "2026-04-23",
    operation_arrival_offset_days: float | None = 1.0,
    operation_arrival_date: str | None = "2026-04-21",
    internal_wait_days: float | None,
    processing_time_days: float | None,
    internal_completion_offset_days: float | None,
    extreme_delay_flag: bool = False,
    alt_machine: str | None = None,
    operation_hours: float = 8.0,
    full_kit_flag: bool = False,
    near_ready_flag: bool = True,
):
    internal_completion_days = None if internal_wait_days is None or processing_time_days is None else internal_wait_days + processing_time_days
    return PlannedOperationSnapshot(
        planned_operation_id=planned_operation_id,
        valve_id="V-100",
        component_line_no=1,
        component="Body",
        operation_name="Op",
        machine_type=machine_type,
        alt_machine=alt_machine,
        subcontract_allowed=subcontract_allowed,
        vendor_process=vendor_process,
        operation_hours=operation_hours,
        operation_arrival_offset_days=operation_arrival_offset_days,
        operation_arrival_date=(None if operation_arrival_date is None else date.fromisoformat(operation_arrival_date)),
        full_kit_flag=full_kit_flag,
        near_ready_flag=near_ready_flag,
        internal_wait_days=internal_wait_days,
        processing_time_days=processing_time_days,
        internal_completion_days=internal_completion_days,
        internal_completion_offset_days=internal_completion_offset_days,
        internal_completion_date=(None if internal_completion_date is None else date.fromisoformat(internal_completion_date)),
        extreme_delay_flag=extreme_delay_flag,
    )


def _machine_summary(
    machine_type: str,
    *,
    overload_flag: bool,
    batch_risk_flag: bool,
    load_days: float,
    buffer_days: float,
    spare_capacity_days: float | None = None,
    total_operation_hours: float | None = None,
    capacity_hours_per_day: float = 8.0,
):
    return MachineLoadSummarySnapshot(
        machine_type=machine_type,
        total_operation_hours=load_days * capacity_hours_per_day if total_operation_hours is None else total_operation_hours,
        capacity_hours_per_day=capacity_hours_per_day,
        load_days=load_days,
        buffer_days=buffer_days,
        spare_capacity_days=(
            max(buffer_days - load_days, 0.0) if spare_capacity_days is None else spare_capacity_days
        ),
        overload_flag=overload_flag,
        batch_risk_flag=batch_risk_flag,
    )


def _vendor(
    vendor_id: str,
    vendor_name: str,
    primary_process: str,
    *,
    turnaround_days: float = 1.0,
    transport_days_total: float = 0.0,
    effective_lead_days: float = 1.0,
    capacity_rating: str | None = "Medium",
    reliability: str | None = "A",
    approved: bool = True,
) -> VendorSnapshot:
    return VendorSnapshot(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        primary_process=primary_process,
        turnaround_days=turnaround_days,
        transport_days_total=transport_days_total,
        effective_lead_days=effective_lead_days,
        capacity_rating=capacity_rating,
        reliability=reliability,
        approved=approved,
    )


def _recommendation_type(
    recommendation_type: str,
    *,
    suggested_vendor_id: str | None = None,
    suggested_vendor_name: str | None = None,
):
    from app.planning.recommendations import RecommendationData

    return RecommendationData(
        planned_operation_id=None,
        recommendation_type=recommendation_type,
        valve_id=None,
        component_line_no=None,
        component=None,
        operation_name=None,
        machine_type=None,
        suggested_machine_type=None,
        suggested_vendor_id=suggested_vendor_id,
        suggested_vendor_name=suggested_vendor_name,
        internal_wait_days=None,
        processing_time_days=None,
        internal_completion_days=None,
        vendor_total_days=None,
        vendor_gain_days=None,
        subcontract_batch_candidate_count=None,
        batch_subcontract_opportunity_flag=False,
        reason_codes=(recommendation_type,),
        explanation=f"{recommendation_type} placeholder.",
        status="PENDING",
        recommendation_status=recommendation_type,
    )
