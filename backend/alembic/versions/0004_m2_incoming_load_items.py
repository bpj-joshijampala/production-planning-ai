"""create m2 incoming load items

Revision ID: 0004_m2_incoming_load_items
Revises: 0003_m2_valve_readiness
Create Date: 2026-04-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_m2_incoming_load_items"
down_revision: str | None = "0003_m2_valve_readiness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incoming_load_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("valve_id", sa.String(), nullable=False),
        sa.Column("component_line_no", sa.Integer(), nullable=False),
        sa.Column("component", sa.String(), nullable=False),
        sa.Column("qty", sa.REAL(), nullable=False),
        sa.Column("availability_date", sa.String(), nullable=False),
        sa.Column("date_confidence", sa.String(), nullable=False),
        sa.Column("current_ready_flag", sa.Integer(), nullable=False),
        sa.Column("machine_types_json", sa.String(), nullable=True),
        sa.Column("priority_score", sa.REAL(), nullable=False),
        sa.Column("sort_sequence", sa.Integer(), nullable=False),
        sa.Column("same_day_arrival_load_days", sa.REAL(), nullable=True),
        sa.Column("batch_risk_flag", sa.Integer(), nullable=False),
        sa.CheckConstraint("qty > 0", name="ck_incoming_load_items_qty_positive"),
        sa.CheckConstraint(
            "date_confidence in ('CONFIRMED', 'EXPECTED', 'TENTATIVE')",
            name="ck_incoming_load_items_date_confidence",
        ),
        sa.CheckConstraint(
            "current_ready_flag in (0, 1)",
            name="ck_incoming_load_items_current_ready_flag_bool",
        ),
        sa.CheckConstraint(
            "machine_types_json is null or json_valid(machine_types_json)",
            name="ck_incoming_load_items_machine_types_json",
        ),
        sa.CheckConstraint(
            "machine_types_json is null or json_type(machine_types_json) = 'array'",
            name="ck_incoming_load_items_machine_types_json_array",
        ),
        sa.CheckConstraint("sort_sequence > 0", name="ck_incoming_load_items_sort_sequence_positive"),
        sa.CheckConstraint(
            "same_day_arrival_load_days is null or same_day_arrival_load_days >= 0",
            name="ck_incoming_load_items_same_day_arrival_load_days_nonnegative",
        ),
        sa.CheckConstraint("batch_risk_flag in (0, 1)", name="ck_incoming_load_items_batch_risk_flag_bool"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_incoming_load_items_planning_run_id"),
        sa.ForeignKeyConstraint(
            ["planning_run_id", "valve_id", "component_line_no"],
            ["component_statuses.planning_run_id", "component_statuses.valve_id", "component_statuses.component_line_no"],
            name="fk_incoming_load_items_run_valve_line",
        ),
        sa.UniqueConstraint(
            "planning_run_id",
            "valve_id",
            "component_line_no",
            name="uq_incoming_load_items_run_valve_line",
        ),
    )
    op.create_index(
        "ix_incoming_load_items_run_availability_date",
        "incoming_load_items",
        ["planning_run_id", "availability_date"],
    )
    op.create_index("ix_incoming_load_items_run_valve", "incoming_load_items", ["planning_run_id", "valve_id"])
    op.create_index(
        "ix_incoming_load_items_run_date_confidence",
        "incoming_load_items",
        ["planning_run_id", "date_confidence"],
    )
    op.create_index(
        "ix_incoming_load_items_run_sort_sequence",
        "incoming_load_items",
        ["planning_run_id", "sort_sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_incoming_load_items_run_sort_sequence", table_name="incoming_load_items")
    op.drop_index("ix_incoming_load_items_run_date_confidence", table_name="incoming_load_items")
    op.drop_index("ix_incoming_load_items_run_valve", table_name="incoming_load_items")
    op.drop_index("ix_incoming_load_items_run_availability_date", table_name="incoming_load_items")
    op.drop_table("incoming_load_items")
