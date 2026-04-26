"""create m2 recommendations and vendor load

Revision ID: 0009_m2_recommendations_and_vendor_load
Revises: 0008_m2_planner_overrides
Create Date: 2026-04-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_m2_recommendations_and_vendor_load"
down_revision: str | None = "0008_m2_planner_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_load_summaries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("vendor_id", sa.String(), nullable=False),
        sa.Column("vendor_name", sa.String(), nullable=False),
        sa.Column("primary_process", sa.String(), nullable=False),
        sa.Column("vendor_recommended_jobs", sa.Integer(), nullable=False),
        sa.Column("max_recommended_jobs_per_horizon", sa.Integer(), nullable=False),
        sa.Column("selected_vendor_overloaded_flag", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.CheckConstraint(
            "vendor_recommended_jobs >= 0",
            name="ck_vendor_load_summaries_vendor_recommended_jobs_nonnegative",
        ),
        sa.CheckConstraint(
            "max_recommended_jobs_per_horizon > 0",
            name="ck_vendor_load_summaries_max_recommended_jobs_positive",
        ),
        sa.CheckConstraint(
            "selected_vendor_overloaded_flag in (0, 1)",
            name="ck_vendor_load_summaries_selected_vendor_overloaded_flag_bool",
        ),
        sa.CheckConstraint(
            "status in ('OK', 'VENDOR_OVERLOADED')",
            name="ck_vendor_load_summaries_status",
        ),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_vendor_load_summaries_planning_run_id"),
        sa.ForeignKeyConstraint(
            ["planning_run_id", "vendor_id"],
            ["vendors.planning_run_id", "vendors.vendor_id"],
            name="fk_vendor_load_summaries_run_vendor",
        ),
        sa.UniqueConstraint(
            "planning_run_id",
            "vendor_id",
            "primary_process",
            name="uq_vendor_load_summaries_run_vendor_process",
        ),
    )
    op.create_index("ix_vendor_load_summaries_run_vendor", "vendor_load_summaries", ["planning_run_id", "vendor_id"])
    op.create_index("ix_vendor_load_summaries_run_status", "vendor_load_summaries", ["planning_run_id", "status"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("planned_operation_id", sa.String(), nullable=True),
        sa.Column("recommendation_type", sa.String(), nullable=False),
        sa.Column("valve_id", sa.String(), nullable=True),
        sa.Column("component_line_no", sa.Integer(), nullable=True),
        sa.Column("component", sa.String(), nullable=True),
        sa.Column("operation_name", sa.String(), nullable=True),
        sa.Column("machine_type", sa.String(), nullable=True),
        sa.Column("suggested_machine_type", sa.String(), nullable=True),
        sa.Column("suggested_vendor_id", sa.String(), nullable=True),
        sa.Column("suggested_vendor_name", sa.String(), nullable=True),
        sa.Column("internal_wait_days", sa.REAL(), nullable=True),
        sa.Column("processing_time_days", sa.REAL(), nullable=True),
        sa.Column("internal_completion_days", sa.REAL(), nullable=True),
        sa.Column("vendor_total_days", sa.REAL(), nullable=True),
        sa.Column("vendor_gain_days", sa.REAL(), nullable=True),
        sa.Column("subcontract_batch_candidate_count", sa.Integer(), nullable=True),
        sa.Column("batch_subcontract_opportunity_flag", sa.Integer(), nullable=False),
        sa.Column("reason_codes_json", sa.String(), nullable=False),
        sa.Column("explanation", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            (
                "recommendation_type in ("
                "'OK_INTERNAL','MACHINE_OVERLOAD','USE_ALTERNATE','SUBCONTRACT',"
                "'HOLD_FOR_PRIORITY_FLOW','EXTREME_DELAY','BATCH_SUBCONTRACT_OPPORTUNITY',"
                "'BATCH_RISK','FLOW_BLOCKER','NO_FEASIBLE_OPTION','DATA_ERROR'"
                ")"
            ),
            name="ck_recommendations_recommendation_type",
        ),
        sa.CheckConstraint(
            "internal_wait_days is null or internal_wait_days >= 0",
            name="ck_recommendations_internal_wait_days_nonnegative",
        ),
        sa.CheckConstraint(
            "processing_time_days is null or processing_time_days >= 0",
            name="ck_recommendations_processing_time_days_nonnegative",
        ),
        sa.CheckConstraint(
            "internal_completion_days is null or internal_completion_days >= 0",
            name="ck_recommendations_internal_completion_days_nonnegative",
        ),
        sa.CheckConstraint(
            "vendor_total_days is null or vendor_total_days >= 0",
            name="ck_recommendations_vendor_total_days_nonnegative",
        ),
        sa.CheckConstraint(
            "vendor_gain_days is null or vendor_gain_days >= 0",
            name="ck_recommendations_vendor_gain_days_nonnegative",
        ),
        sa.CheckConstraint(
            "subcontract_batch_candidate_count is null or subcontract_batch_candidate_count >= 0",
            name="ck_recommendations_subcontract_batch_candidate_count_nonnegative",
        ),
        sa.CheckConstraint(
            "batch_subcontract_opportunity_flag in (0, 1)",
            name="ck_recommendations_batch_subcontract_opportunity_flag_bool",
        ),
        sa.CheckConstraint(
            "json_valid(reason_codes_json) and json_type(reason_codes_json) = 'array'",
            name="ck_recommendations_reason_codes_json",
        ),
        sa.CheckConstraint(
            "status in ('PENDING', 'ACCEPTED', 'REJECTED', 'OVERRIDDEN')",
            name="ck_recommendations_status",
        ),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_recommendations_planning_run_id"),
        sa.ForeignKeyConstraint(["planned_operation_id"], ["planned_operations.id"], name="fk_recommendations_planned_operation_id"),
    )
    op.create_index("ix_recommendations_run_type", "recommendations", ["planning_run_id", "recommendation_type"])
    op.create_index("ix_recommendations_run_status", "recommendations", ["planning_run_id", "status"])
    op.create_index("ix_recommendations_run_vendor", "recommendations", ["planning_run_id", "suggested_vendor_id"])
    op.create_index("ix_recommendations_planned_operation", "recommendations", ["planned_operation_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_planned_operation", table_name="recommendations")
    op.drop_index("ix_recommendations_run_vendor", table_name="recommendations")
    op.drop_index("ix_recommendations_run_status", table_name="recommendations")
    op.drop_index("ix_recommendations_run_type", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_vendor_load_summaries_run_status", table_name="vendor_load_summaries")
    op.drop_index("ix_vendor_load_summaries_run_vendor", table_name="vendor_load_summaries")
    op.drop_table("vendor_load_summaries")
