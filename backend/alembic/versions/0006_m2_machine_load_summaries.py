"""create m2 machine load summaries

Revision ID: 0006_m2_machine_load_summaries
Revises: 0005_m2_planned_operations_and_flow_blockers
Create Date: 2026-04-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_m2_machine_load_summaries"
down_revision: str | None = "0005_m2_planned_operations_and_flow_blockers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "machine_load_summaries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("machine_type", sa.String(), nullable=False),
        sa.Column("total_operation_hours", sa.REAL(), nullable=False),
        sa.Column("capacity_hours_per_day", sa.REAL(), nullable=False),
        sa.Column("load_days", sa.REAL(), nullable=False),
        sa.Column("buffer_days", sa.REAL(), nullable=False),
        sa.Column("overload_flag", sa.Integer(), nullable=False),
        sa.Column("overload_days", sa.REAL(), nullable=False),
        sa.Column("spare_capacity_days", sa.REAL(), nullable=False),
        sa.Column("underutilized_flag", sa.Integer(), nullable=False),
        sa.Column("batch_risk_flag", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.CheckConstraint(
            "total_operation_hours >= 0",
            name="ck_machine_load_summaries_total_operation_hours_nonnegative",
        ),
        sa.CheckConstraint(
            "capacity_hours_per_day >= 0",
            name="ck_machine_load_summaries_capacity_hours_per_day_nonnegative",
        ),
        sa.CheckConstraint("load_days >= 0", name="ck_machine_load_summaries_load_days_nonnegative"),
        sa.CheckConstraint("buffer_days >= 0", name="ck_machine_load_summaries_buffer_days_nonnegative"),
        sa.CheckConstraint("overload_flag in (0, 1)", name="ck_machine_load_summaries_overload_flag_bool"),
        sa.CheckConstraint("overload_days >= 0", name="ck_machine_load_summaries_overload_days_nonnegative"),
        sa.CheckConstraint(
            "spare_capacity_days >= 0",
            name="ck_machine_load_summaries_spare_capacity_days_nonnegative",
        ),
        sa.CheckConstraint(
            "underutilized_flag in (0, 1)",
            name="ck_machine_load_summaries_underutilized_flag_bool",
        ),
        sa.CheckConstraint("batch_risk_flag in (0, 1)", name="ck_machine_load_summaries_batch_risk_flag_bool"),
        sa.CheckConstraint(
            "status in ('OK', 'OVERLOADED', 'UNDERUTILIZED', 'DATA_INCOMPLETE')",
            name="ck_machine_load_summaries_status",
        ),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_machine_load_summaries_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", "machine_type", name="uq_machine_load_summaries_run_machine_type"),
    )
    op.create_index(
        "ix_machine_load_summaries_run_machine_type",
        "machine_load_summaries",
        ["planning_run_id", "machine_type"],
    )
    op.create_index("ix_machine_load_summaries_run_status", "machine_load_summaries", ["planning_run_id", "status"])
    op.create_index(
        "ix_machine_load_summaries_run_overload_flag",
        "machine_load_summaries",
        ["planning_run_id", "overload_flag"],
    )
    op.create_index(
        "ix_machine_load_summaries_run_underutilized_flag",
        "machine_load_summaries",
        ["planning_run_id", "underutilized_flag"],
    )


def downgrade() -> None:
    op.drop_index("ix_machine_load_summaries_run_underutilized_flag", table_name="machine_load_summaries")
    op.drop_index("ix_machine_load_summaries_run_overload_flag", table_name="machine_load_summaries")
    op.drop_index("ix_machine_load_summaries_run_status", table_name="machine_load_summaries")
    op.drop_index("ix_machine_load_summaries_run_machine_type", table_name="machine_load_summaries")
    op.drop_table("machine_load_summaries")
