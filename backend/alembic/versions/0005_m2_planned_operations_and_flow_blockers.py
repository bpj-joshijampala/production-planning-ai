"""create m2 planned operations and flow blockers

Revision ID: 0005_m2_planned_operations_and_flow_blockers
Revises: 0004_m2_incoming_load_items
Create Date: 2026-04-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_m2_planned_operations_and_flow_blockers"
down_revision: str | None = "0004_m2_incoming_load_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planned_operations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("valve_id", sa.String(), nullable=False),
        sa.Column("component_line_no", sa.Integer(), nullable=False),
        sa.Column("component", sa.String(), nullable=False),
        sa.Column("operation_no", sa.Integer(), nullable=False),
        sa.Column("operation_name", sa.String(), nullable=False),
        sa.Column("machine_type", sa.String(), nullable=False),
        sa.Column("alt_machine", sa.String(), nullable=True),
        sa.Column("qty", sa.REAL(), nullable=False),
        sa.Column("operation_hours", sa.REAL(), nullable=False),
        sa.Column("availability_date", sa.String(), nullable=False),
        sa.Column("date_confidence", sa.String(), nullable=False),
        sa.Column("priority_score", sa.REAL(), nullable=False),
        sa.Column("sort_sequence", sa.Integer(), nullable=False),
        sa.Column("availability_offset_days", sa.REAL(), nullable=False),
        sa.Column("operation_arrival_offset_days", sa.REAL(), nullable=True),
        sa.Column("operation_arrival_date", sa.String(), nullable=True),
        sa.Column("scheduled_start_offset_days", sa.REAL(), nullable=True),
        sa.Column("internal_wait_days", sa.REAL(), nullable=True),
        sa.Column("processing_time_days", sa.REAL(), nullable=True),
        sa.Column("internal_completion_days", sa.REAL(), nullable=True),
        sa.Column("internal_completion_offset_days", sa.REAL(), nullable=True),
        sa.Column("internal_completion_date", sa.String(), nullable=True),
        sa.Column("extreme_delay_flag", sa.Integer(), nullable=True),
        sa.Column("recommendation_status", sa.String(), nullable=True),
        sa.CheckConstraint("operation_no > 0", name="ck_planned_operations_operation_no_positive"),
        sa.CheckConstraint("qty > 0", name="ck_planned_operations_qty_positive"),
        sa.CheckConstraint("operation_hours > 0", name="ck_planned_operations_operation_hours_positive"),
        sa.CheckConstraint(
            "date_confidence in ('CONFIRMED', 'EXPECTED', 'TENTATIVE')",
            name="ck_planned_operations_date_confidence",
        ),
        sa.CheckConstraint("sort_sequence > 0", name="ck_planned_operations_sort_sequence_positive"),
        sa.CheckConstraint(
            "availability_offset_days >= 0",
            name="ck_planned_operations_availability_offset_days_nonnegative",
        ),
        sa.CheckConstraint(
            "operation_arrival_offset_days is null or operation_arrival_offset_days >= 0",
            name="ck_planned_operations_operation_arrival_offset_days_nonnegative",
        ),
        sa.CheckConstraint(
            "scheduled_start_offset_days is null or scheduled_start_offset_days >= 0",
            name="ck_planned_operations_scheduled_start_offset_days_nonnegative",
        ),
        sa.CheckConstraint(
            "internal_wait_days is null or internal_wait_days >= 0",
            name="ck_planned_operations_internal_wait_days_nonnegative",
        ),
        sa.CheckConstraint(
            "processing_time_days is null or processing_time_days >= 0",
            name="ck_planned_operations_processing_time_days_nonnegative",
        ),
        sa.CheckConstraint(
            "internal_completion_days is null or internal_completion_days >= 0",
            name="ck_planned_operations_internal_completion_days_nonnegative",
        ),
        sa.CheckConstraint(
            "internal_completion_offset_days is null or internal_completion_offset_days >= 0",
            name="ck_planned_operations_internal_completion_offset_days_nonnegative",
        ),
        sa.CheckConstraint(
            "extreme_delay_flag is null or extreme_delay_flag in (0, 1)",
            name="ck_planned_operations_extreme_delay_flag_bool",
        ),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_planned_operations_planning_run_id"),
        sa.ForeignKeyConstraint(
            ["planning_run_id", "valve_id", "component_line_no"],
            ["component_statuses.planning_run_id", "component_statuses.valve_id", "component_statuses.component_line_no"],
            name="fk_planned_operations_run_valve_line",
        ),
        sa.UniqueConstraint(
            "planning_run_id",
            "valve_id",
            "component_line_no",
            "operation_no",
            name="uq_planned_operations_run_valve_line_operation",
        ),
    )
    op.create_index("ix_planned_operations_run_machine_type", "planned_operations", ["planning_run_id", "machine_type"])
    op.create_index("ix_planned_operations_run_valve", "planned_operations", ["planning_run_id", "valve_id"])
    op.create_index(
        "ix_planned_operations_run_internal_completion_date",
        "planned_operations",
        ["planning_run_id", "internal_completion_date"],
    )
    op.create_index("ix_planned_operations_run_sort_sequence", "planned_operations", ["planning_run_id", "sort_sequence"])
    op.create_index(
        "ix_planned_operations_run_extreme_delay_flag",
        "planned_operations",
        ["planning_run_id", "extreme_delay_flag"],
    )

    op.create_table(
        "flow_blockers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("planned_operation_id", sa.String(), nullable=True),
        sa.Column("valve_id", sa.String(), nullable=True),
        sa.Column("component_line_no", sa.Integer(), nullable=True),
        sa.Column("component", sa.String(), nullable=True),
        sa.Column("operation_name", sa.String(), nullable=True),
        sa.Column("blocker_type", sa.String(), nullable=False),
        sa.Column("cause", sa.String(), nullable=False),
        sa.Column("recommended_action", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            (
                "blocker_type in ("
                "'MISSING_COMPONENT','MISSING_ROUTING','MISSING_MACHINE','MACHINE_OVERLOAD','BATCH_RISK',"
                "'FLOW_GAP','VALVE_FLOW_IMBALANCE','EXTREME_DELAY','VENDOR_UNAVAILABLE','VENDOR_OVERLOADED'"
                ")"
            ),
            name="ck_flow_blockers_blocker_type",
        ),
        sa.CheckConstraint("severity in ('INFO', 'WARNING', 'CRITICAL')", name="ck_flow_blockers_severity"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_flow_blockers_planning_run_id"),
        sa.ForeignKeyConstraint(["planned_operation_id"], ["planned_operations.id"], name="fk_flow_blockers_planned_operation_id"),
    )
    op.create_index("ix_flow_blockers_run_blocker_type", "flow_blockers", ["planning_run_id", "blocker_type"])
    op.create_index("ix_flow_blockers_run_severity", "flow_blockers", ["planning_run_id", "severity"])
    op.create_index("ix_flow_blockers_run_valve", "flow_blockers", ["planning_run_id", "valve_id"])


def downgrade() -> None:
    op.drop_index("ix_flow_blockers_run_valve", table_name="flow_blockers")
    op.drop_index("ix_flow_blockers_run_severity", table_name="flow_blockers")
    op.drop_index("ix_flow_blockers_run_blocker_type", table_name="flow_blockers")
    op.drop_table("flow_blockers")

    op.drop_index("ix_planned_operations_run_extreme_delay_flag", table_name="planned_operations")
    op.drop_index("ix_planned_operations_run_sort_sequence", table_name="planned_operations")
    op.drop_index("ix_planned_operations_run_internal_completion_date", table_name="planned_operations")
    op.drop_index("ix_planned_operations_run_valve", table_name="planned_operations")
    op.drop_index("ix_planned_operations_run_machine_type", table_name="planned_operations")
    op.drop_table("planned_operations")
