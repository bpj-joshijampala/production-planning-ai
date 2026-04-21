"""create app metadata

Revision ID: 0001_app_metadata
Revises:
Create Date: 2026-04-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_app_metadata"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("key", name="uq_app_metadata_key"),
    )
    op.bulk_insert(
        sa.table(
            "app_metadata",
            sa.column("key", sa.String),
            sa.column("value", sa.String),
        ),
        [{"key": "schema_baseline", "value": "m0"}],
    )


def downgrade() -> None:
    op.drop_table("app_metadata")
