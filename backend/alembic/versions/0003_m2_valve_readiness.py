"""create m2 valve readiness summaries

Revision ID: 0003_m2_valve_readiness
Revises: 0002_m1_data_foundation
Create Date: 2026-04-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_m2_valve_readiness"
down_revision: str | None = "0002_m1_data_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "valve_readiness_summaries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("valve_id", sa.String(), nullable=False),
        sa.Column("customer", sa.String(), nullable=False),
        sa.Column("assembly_date", sa.String(), nullable=False),
        sa.Column("dispatch_date", sa.String(), nullable=False),
        sa.Column("value_cr", sa.REAL(), nullable=False),
        sa.Column("total_components", sa.Integer(), nullable=False),
        sa.Column("ready_components", sa.Integer(), nullable=False),
        sa.Column("required_components", sa.Integer(), nullable=False),
        sa.Column("ready_required_count", sa.Integer(), nullable=False),
        sa.Column("pending_required_count", sa.Integer(), nullable=False),
        sa.Column("full_kit_flag", sa.Integer(), nullable=False),
        sa.Column("near_ready_flag", sa.Integer(), nullable=False),
        sa.Column("valve_expected_completion_offset_days", sa.REAL(), nullable=True),
        sa.Column("valve_expected_completion_date", sa.String(), nullable=True),
        sa.Column("otd_delay_days", sa.REAL(), nullable=False),
        sa.Column("otd_risk_flag", sa.Integer(), nullable=False),
        sa.Column("readiness_status", sa.String(), nullable=False),
        sa.Column("risk_reason", sa.String(), nullable=True),
        sa.Column("valve_flow_gap_days", sa.REAL(), nullable=True),
        sa.Column("valve_flow_imbalance_flag", sa.Integer(), nullable=False),
        sa.CheckConstraint("value_cr >= 0", name="ck_valve_readiness_summaries_value_cr_nonnegative"),
        sa.CheckConstraint("total_components >= 0", name="ck_valve_readiness_summaries_total_components_nonnegative"),
        sa.CheckConstraint("ready_components >= 0", name="ck_valve_readiness_summaries_ready_components_nonnegative"),
        sa.CheckConstraint(
            "required_components >= 0",
            name="ck_valve_readiness_summaries_required_components_nonnegative",
        ),
        sa.CheckConstraint(
            "ready_required_count >= 0",
            name="ck_valve_readiness_summaries_ready_required_count_nonnegative",
        ),
        sa.CheckConstraint(
            "pending_required_count >= 0",
            name="ck_valve_readiness_summaries_pending_required_count_nonnegative",
        ),
        sa.CheckConstraint("full_kit_flag in (0, 1)", name="ck_valve_readiness_summaries_full_kit_flag_bool"),
        sa.CheckConstraint("near_ready_flag in (0, 1)", name="ck_valve_readiness_summaries_near_ready_flag_bool"),
        sa.CheckConstraint("otd_delay_days >= 0", name="ck_valve_readiness_summaries_otd_delay_days_nonnegative"),
        sa.CheckConstraint("otd_risk_flag in (0, 1)", name="ck_valve_readiness_summaries_otd_risk_flag_bool"),
        sa.CheckConstraint(
            "readiness_status in ('READY', 'NEAR_READY', 'NOT_READY', 'AT_RISK', 'DATA_INCOMPLETE')",
            name="ck_valve_readiness_summaries_readiness_status",
        ),
        sa.CheckConstraint(
            "valve_flow_imbalance_flag in (0, 1)",
            name="ck_valve_readiness_summaries_valve_flow_imbalance_flag_bool",
        ),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_valve_readiness_summaries_planning_run_id"),
        sa.ForeignKeyConstraint(
            ["planning_run_id", "valve_id"],
            ["valves.planning_run_id", "valves.valve_id"],
            name="fk_valve_readiness_summaries_run_valve",
        ),
        sa.UniqueConstraint("planning_run_id", "valve_id", name="uq_valve_readiness_summaries_run_valve"),
    )
    op.create_index(
        "ix_valve_readiness_summaries_run_status",
        "valve_readiness_summaries",
        ["planning_run_id", "readiness_status"],
    )
    op.create_index(
        "ix_valve_readiness_summaries_run_otd_risk",
        "valve_readiness_summaries",
        ["planning_run_id", "otd_risk_flag"],
    )
    op.create_index(
        "ix_valve_readiness_summaries_run_assembly_date",
        "valve_readiness_summaries",
        ["planning_run_id", "assembly_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_valve_readiness_summaries_run_assembly_date", table_name="valve_readiness_summaries")
    op.drop_index("ix_valve_readiness_summaries_run_otd_risk", table_name="valve_readiness_summaries")
    op.drop_index("ix_valve_readiness_summaries_run_status", table_name="valve_readiness_summaries")
    op.drop_table("valve_readiness_summaries")
