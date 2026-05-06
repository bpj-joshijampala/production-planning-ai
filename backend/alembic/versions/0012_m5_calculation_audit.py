"""add planning run calculation actor

Revision ID: 0012_m5_calculation_audit
Revises: 0011_m5_report_exports
Create Date: 2026-05-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0012_m5_calculation_audit"
down_revision: str | None = "0011_m5_report_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("planning_runs") as batch_op:
        batch_op.add_column(sa.Column("calculated_by_user_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_planning_runs_calculated_by_user_id",
            "users",
            ["calculated_by_user_id"],
            ["id"],
        )
        batch_op.create_index("ix_planning_runs_calculated_by_user_id", ["calculated_by_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("planning_runs") as batch_op:
        batch_op.drop_index("ix_planning_runs_calculated_by_user_id")
        batch_op.drop_constraint("fk_planning_runs_calculated_by_user_id", type_="foreignkey")
        batch_op.drop_column("calculated_by_user_id")
