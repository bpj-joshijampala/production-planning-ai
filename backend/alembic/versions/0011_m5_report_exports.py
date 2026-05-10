"""create report exports table

Revision ID: 0011_m5_report_exports
Revises: 0010_m2_machine_load_queue_warning
Create Date: 2026-05-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_m5_report_exports"
down_revision = "0010_m2_machine_load_queue_warning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_exports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("report_type", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("file_format", sa.String(), nullable=False),
        sa.Column("generated_by_user_id", sa.String(), nullable=False),
        sa.Column("generated_at", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.String(), nullable=True),
        sa.CheckConstraint(
            (
                "report_type in ("
                "'MACHINE_LOAD','SUBCONTRACT_PLAN','VALVE_READINESS',"
                "'FLOW_BLOCKER','WEEKLY_PLANNING','DAILY_EXECUTION','A3_PLANNING'"
                ")"
            ),
            name="ck_report_exports_report_type",
        ),
        sa.CheckConstraint("file_format = 'XLSX'", name="ck_report_exports_file_format"),
        sa.CheckConstraint("length(trim(file_path)) > 0", name="ck_report_exports_file_path_not_blank"),
        sa.CheckConstraint("metadata_json is null or json_valid(metadata_json)", name="ck_report_exports_metadata_json"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_exports_run_report_type", "report_exports", ["planning_run_id", "report_type"])
    op.create_index("ix_report_exports_generated_at", "report_exports", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_report_exports_generated_at", table_name="report_exports")
    op.drop_index("ix_report_exports_run_report_type", table_name="report_exports")
    op.drop_table("report_exports")
