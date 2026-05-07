"""allow planning snapshot history

Revision ID: 0013_m5_snapshot_history
Revises: 0012_m5_calculation_audit
Create Date: 2026-05-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_m5_snapshot_history"
down_revision: str | None = "0012_m5_calculation_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("planning_snapshots") as batch_op:
        batch_op.drop_constraint("uq_planning_snapshots_planning_run_id", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("planning_snapshots") as batch_op:
        batch_op.create_unique_constraint("uq_planning_snapshots_planning_run_id", ["planning_run_id"])
