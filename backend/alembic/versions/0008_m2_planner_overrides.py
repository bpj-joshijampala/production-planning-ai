"""create m2 planner overrides

Revision ID: 0008_m2_planner_overrides
Revises: 0007_m2_throughput_summaries
Create Date: 2026-04-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_m2_planner_overrides"
down_revision: str | None = "0007_m2_throughput_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planner_overrides",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("recommendation_id", sa.String(), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("original_recommendation", sa.String(), nullable=True),
        sa.Column("override_decision", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("remarks", sa.String(), nullable=True),
        sa.Column("stale_flag", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            "entity_type in ('RECOMMENDATION', 'OPERATION', 'VALVE', 'MACHINE', 'VENDOR')",
            name="ck_planner_overrides_entity_type",
        ),
        sa.CheckConstraint("length(trim(entity_id)) > 0", name="ck_planner_overrides_entity_id_not_blank"),
        sa.CheckConstraint(
            "length(trim(override_decision)) > 0",
            name="ck_planner_overrides_override_decision_not_blank",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_planner_overrides_reason_not_blank"),
        sa.CheckConstraint("stale_flag in (0, 1)", name="ck_planner_overrides_stale_flag_bool"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_planner_overrides_planning_run_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_planner_overrides_user_id"),
    )
    op.create_index("ix_planner_overrides_run", "planner_overrides", ["planning_run_id"])
    op.create_index("ix_planner_overrides_recommendation", "planner_overrides", ["recommendation_id"])
    op.create_index("ix_planner_overrides_user", "planner_overrides", ["user_id"])
    op.create_index("ix_planner_overrides_stale_flag", "planner_overrides", ["stale_flag"])


def downgrade() -> None:
    op.drop_index("ix_planner_overrides_stale_flag", table_name="planner_overrides")
    op.drop_index("ix_planner_overrides_user", table_name="planner_overrides")
    op.drop_index("ix_planner_overrides_recommendation", table_name="planner_overrides")
    op.drop_index("ix_planner_overrides_run", table_name="planner_overrides")
    op.drop_table("planner_overrides")
