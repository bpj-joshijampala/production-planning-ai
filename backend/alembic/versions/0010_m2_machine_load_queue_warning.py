"""persist machine-load queue approximation warning

Revision ID: 0010_m2_machine_load_queue_warning
Revises: 0009_m2_recommendations_and_vendor_load
Create Date: 2026-04-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_m2_machine_load_queue_warning"
down_revision = "0009_m2_recommendations_and_vendor_load"
branch_labels = None
depends_on = None


QUEUE_WARNING = "Queue is priority-based and aggregated by machine type. Review before execution."


def upgrade() -> None:
    op.add_column(
        "machine_load_summaries",
        sa.Column(
            "queue_approximation_warning",
            sa.String(),
            nullable=False,
            server_default=QUEUE_WARNING,
        ),
    )


def downgrade() -> None:
    op.drop_column("machine_load_summaries", "queue_approximation_warning")
