from datetime import date

from app.planning.recommendations import (
    MachineLoadSummarySnapshot,
    PlannedOperationSnapshot,
    VendorLoadSummaryData,
    calculate_placeholder_recommendations,
    calculate_vendor_load_summaries,
)


def test_calculate_placeholder_recommendations_assigns_expected_precedence() -> None:
    recommendations = calculate_placeholder_recommendations(
        planned_operations=(
            _operation("op-data", "HBM", internal_completion_date=None, internal_wait_days=None, processing_time_days=None),
            _operation("op-delay", "VTL", extreme_delay_flag=True, internal_wait_days=7.0, processing_time_days=1.0),
            _operation("op-overload", "HBM", internal_wait_days=1.0, processing_time_days=1.0),
            _operation("op-batch", "Lathe", internal_wait_days=0.5, processing_time_days=0.5),
            _operation("op-ok", "Drill", internal_wait_days=0.0, processing_time_days=0.25),
        ),
        machine_load_summaries=(
            _machine_summary("HBM", overload_flag=True, batch_risk_flag=False, load_days=6.0, buffer_days=4.0),
            _machine_summary("VTL", overload_flag=False, batch_risk_flag=False, load_days=1.0, buffer_days=3.0),
            _machine_summary("Lathe", overload_flag=False, batch_risk_flag=True, load_days=1.0, buffer_days=3.0),
            _machine_summary("Drill", overload_flag=False, batch_risk_flag=False, load_days=0.5, buffer_days=2.0),
        ),
    )

    assert [(row.planned_operation_id, row.recommendation_type) for row in recommendations] == [
        ("op-data", "DATA_ERROR"),
        ("op-delay", "EXTREME_DELAY"),
        ("op-overload", "MACHINE_OVERLOAD"),
        ("op-batch", "BATCH_RISK"),
        ("op-ok", "OK_INTERNAL"),
    ]
    assert recommendations[0].reason_codes == ("DATA_ERROR",)
    assert recommendations[1].reason_codes == ("EXTREME_DELAY",)
    assert recommendations[2].reason_codes == ("MACHINE_OVERLOAD",)
    assert recommendations[3].reason_codes == ("BATCH_RISK",)
    assert recommendations[4].status == "PENDING"


def test_calculate_vendor_load_summaries_counts_subcontract_recommendations_by_vendor() -> None:
    summaries = calculate_vendor_load_summaries(
        vendors=(
            ("VEN-1", "Vendor One", "HBM", "Medium"),
            ("VEN-2", "Vendor Two", "VTL", "Low"),
            ("VEN-3", "Vendor Three", "Drill", None),
        ),
        recommendations=(
            _recommendation_type("SUBCONTRACT", suggested_vendor_id="VEN-1", suggested_vendor_name="Vendor One"),
            _recommendation_type("SUBCONTRACT", suggested_vendor_id="VEN-1", suggested_vendor_name="Vendor One"),
            _recommendation_type("BATCH_RISK"),
        ),
    )

    assert [(row.vendor_id, row.vendor_recommended_jobs, row.max_recommended_jobs_per_horizon, row.status) for row in summaries] == [
        ("VEN-1", 2, 3, "OK"),
        ("VEN-2", 0, 1, "OK"),
        ("VEN-3", 0, 1, "OK"),
    ]
    assert all(isinstance(row, VendorLoadSummaryData) for row in summaries)


def _operation(
    planned_operation_id: str,
    machine_type: str,
    *,
    internal_completion_date: str | None = "2026-04-23",
    internal_wait_days: float | None,
    processing_time_days: float | None,
    extreme_delay_flag: bool = False,
):
    return PlannedOperationSnapshot(
        planned_operation_id=planned_operation_id,
        valve_id="V-100",
        component_line_no=1,
        component="Body",
        operation_name="Op",
        machine_type=machine_type,
        internal_wait_days=internal_wait_days,
        processing_time_days=processing_time_days,
        internal_completion_days=None if internal_wait_days is None or processing_time_days is None else internal_wait_days + processing_time_days,
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
):
    return MachineLoadSummarySnapshot(
        machine_type=machine_type,
        load_days=load_days,
        buffer_days=buffer_days,
        overload_flag=overload_flag,
        batch_risk_flag=batch_risk_flag,
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
