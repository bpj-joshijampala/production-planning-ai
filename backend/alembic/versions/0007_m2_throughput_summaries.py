"""create m2 throughput summaries

Revision ID: 0007_m2_throughput_summaries
Revises: 0006_m2_machine_load_summaries
Create Date: 2026-04-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_m2_throughput_summaries"
down_revision: str | None = "0006_m2_machine_load_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "throughput_summaries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("target_throughput_value_cr", sa.REAL(), nullable=False),
        sa.Column("planned_throughput_value_cr", sa.REAL(), nullable=False),
        sa.Column("throughput_gap_cr", sa.REAL(), nullable=False),
        sa.Column("throughput_risk_flag", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "target_throughput_value_cr >= 0",
            name="ck_throughput_summaries_target_throughput_value_cr_nonnegative",
        ),
        sa.CheckConstraint(
            "planned_throughput_value_cr >= 0",
            name="ck_throughput_summaries_planned_throughput_value_cr_nonnegative",
        ),
        sa.CheckConstraint(
            "throughput_gap_cr >= 0",
            name="ck_throughput_summaries_throughput_gap_cr_nonnegative",
        ),
        sa.CheckConstraint(
            "throughput_risk_flag in (0, 1)",
            name="ck_throughput_summaries_throughput_risk_flag_bool",
        ),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_throughput_summaries_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", name="uq_throughput_summaries_run"),
    )
    op.create_index(
        "ix_throughput_summaries_run_risk_flag",
        "throughput_summaries",
        ["planning_run_id", "throughput_risk_flag"],
    )


def downgrade() -> None:
    op.drop_index("ix_throughput_summaries_run_risk_flag", table_name="throughput_summaries")
    op.drop_table("throughput_summaries")
