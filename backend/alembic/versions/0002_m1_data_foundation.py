"""create m1 data foundation

Revision ID: 0002_m1_data_foundation
Revises: 0001_app_metadata
Create Date: 2026-04-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_m1_data_foundation"
down_revision: str | None = "0001_app_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=True),
        sa.CheckConstraint("role in ('PLANNER', 'HOD', 'MANAGEMENT', 'ADMIN')", name="ck_users_role"),
        sa.CheckConstraint("active in (0, 1)", name="ck_users_active_bool"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_active", "users", ["active"])

    op.bulk_insert(
        sa.table(
            "users",
            sa.column("id", sa.String),
            sa.column("username", sa.String),
            sa.column("display_name", sa.String),
            sa.column("role", sa.String),
            sa.column("active", sa.Integer),
            sa.column("created_at", sa.String),
        ),
        [
            {
                "id": DEV_USER_ID,
                "username": "dev.planner",
                "display_name": "Development Planner",
                "role": "PLANNER",
                "active": 1,
                "created_at": "2026-04-21T00:00:00Z",
            }
        ],
    )

    op.create_table(
        "upload_batches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("stored_filename", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(), nullable=False),
        sa.Column("uploaded_at", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("validation_error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "status in ('UPLOADED', 'VALIDATION_FAILED', 'VALIDATED', 'PROMOTED', 'CALCULATED')",
            name="ck_upload_batches_status",
        ),
        sa.CheckConstraint("file_size_bytes > 0", name="ck_upload_batches_file_size_positive"),
        sa.CheckConstraint("validation_error_count >= 0", name="ck_upload_batches_error_count_nonnegative"),
        sa.CheckConstraint("validation_warning_count >= 0", name="ck_upload_batches_warning_count_nonnegative"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], name="fk_upload_batches_uploaded_by_user_id"),
    )
    op.create_index("ix_upload_batches_uploaded_at", "upload_batches", ["uploaded_at"])
    op.create_index("ix_upload_batches_uploaded_by_user_id", "upload_batches", ["uploaded_by_user_id"])
    op.create_index("ix_upload_batches_status", "upload_batches", ["status"])
    op.create_index("ix_upload_batches_file_hash", "upload_batches", ["file_hash"])

    op.create_table(
        "raw_upload_artifacts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("upload_batch_id", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], name="fk_raw_upload_artifacts_upload_batch_id"),
        sa.UniqueConstraint("upload_batch_id", name="uq_raw_upload_artifacts_upload_batch_id"),
    )

    op.create_table(
        "import_staging_rows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("upload_batch_id", sa.String(), nullable=False),
        sa.Column("sheet_name", sa.String(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("normalized_payload_json", sa.String(), nullable=False),
        sa.Column("row_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint("json_valid(normalized_payload_json)", name="ck_import_staging_rows_payload_json"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], name="fk_import_staging_rows_upload_batch_id"),
    )
    op.create_index("ix_import_staging_rows_upload_sheet", "import_staging_rows", ["upload_batch_id", "sheet_name"])
    op.create_index(
        "ix_import_staging_rows_upload_sheet_row",
        "import_staging_rows",
        ["upload_batch_id", "sheet_name", "row_number"],
    )

    op.create_table(
        "import_validation_issues",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("upload_batch_id", sa.String(), nullable=False),
        sa.Column("staging_row_id", sa.String(), nullable=True),
        sa.Column("sheet_name", sa.String(), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("issue_code", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint("severity in ('BLOCKING', 'WARNING')", name="ck_import_validation_issues_severity"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], name="fk_import_validation_issues_upload_batch_id"),
        sa.ForeignKeyConstraint(["staging_row_id"], ["import_staging_rows.id"], name="fk_import_validation_issues_staging_row_id"),
    )
    op.create_index(
        "ix_import_validation_issues_upload_severity",
        "import_validation_issues",
        ["upload_batch_id", "severity"],
    )
    op.create_index(
        "ix_import_validation_issues_upload_sheet_row",
        "import_validation_issues",
        ["upload_batch_id", "sheet_name", "row_number"],
    )
    op.create_index("ix_import_validation_issues_issue_code", "import_validation_issues", ["issue_code"])

    op.create_table(
        "planning_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("upload_batch_id", sa.String(), nullable=False),
        sa.Column("planning_start_date", sa.String(), nullable=False),
        sa.Column("planning_horizon_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("calculated_at", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.CheckConstraint("planning_horizon_days in (7, 14)", name="ck_planning_runs_horizon"),
        sa.CheckConstraint("status in ('CREATED', 'CALCULATING', 'CALCULATED', 'FAILED')", name="ck_planning_runs_status"),
        sa.ForeignKeyConstraint(["upload_batch_id"], ["upload_batches.id"], name="fk_planning_runs_upload_batch_id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_planning_runs_created_by_user_id"),
    )
    op.create_index("ix_planning_runs_upload_batch_id", "planning_runs", ["upload_batch_id"])
    op.create_index("ix_planning_runs_created_at", "planning_runs", ["created_at"])
    op.create_index("ix_planning_runs_status", "planning_runs", ["status"])
    op.create_index("ix_planning_runs_planning_start_date", "planning_runs", ["planning_start_date"])

    op.create_table(
        "planning_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("snapshot_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint("json_valid(snapshot_json)", name="ck_planning_snapshots_snapshot_json"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_planning_snapshots_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", name="uq_planning_snapshots_planning_run_id"),
    )

    op.create_table(
        "master_data_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("routing_version_hash", sa.String(), nullable=False),
        sa.Column("machine_version_hash", sa.String(), nullable=False),
        sa.Column("vendor_version_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_master_data_versions_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", name="uq_master_data_versions_planning_run_id"),
    )

    op.create_table(
        "valves",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("valve_id", sa.String(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("customer", sa.String(), nullable=False),
        sa.Column("valve_type", sa.String(), nullable=True),
        sa.Column("dispatch_date", sa.String(), nullable=False),
        sa.Column("assembly_date", sa.String(), nullable=False),
        sa.Column("value_cr", sa.REAL(), nullable=False),
        sa.Column("priority", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("remarks", sa.String(), nullable=True),
        sa.CheckConstraint("value_cr >= 0", name="ck_valves_value_cr_nonnegative"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_valves_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", "valve_id", name="uq_valves_run_valve_id"),
    )
    op.create_index("ix_valves_run_assembly_date", "valves", ["planning_run_id", "assembly_date"])
    op.create_index("ix_valves_run_dispatch_date", "valves", ["planning_run_id", "dispatch_date"])
    op.create_index("ix_valves_run_customer", "valves", ["planning_run_id", "customer"])
    op.create_index("ix_valves_run_priority", "valves", ["planning_run_id", "priority"])

    op.create_table(
        "component_statuses",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("valve_id", sa.String(), nullable=False),
        sa.Column("component_line_no", sa.Integer(), nullable=False),
        sa.Column("component", sa.String(), nullable=False),
        sa.Column("qty", sa.REAL(), nullable=False),
        sa.Column("fabrication_required", sa.Integer(), nullable=False),
        sa.Column("fabrication_complete", sa.Integer(), nullable=False),
        sa.Column("expected_ready_date", sa.String(), nullable=False),
        sa.Column("critical", sa.Integer(), nullable=False),
        sa.Column("expected_from_fabrication", sa.String(), nullable=True),
        sa.Column("priority_eligible", sa.Integer(), nullable=True),
        sa.Column("ready_date_type", sa.String(), nullable=False),
        sa.Column("current_location", sa.String(), nullable=True),
        sa.Column("comments", sa.String(), nullable=True),
        sa.CheckConstraint("qty > 0", name="ck_component_statuses_qty_positive"),
        sa.CheckConstraint("fabrication_required in (0, 1)", name="ck_component_statuses_fabrication_required_bool"),
        sa.CheckConstraint("fabrication_complete in (0, 1)", name="ck_component_statuses_fabrication_complete_bool"),
        sa.CheckConstraint("critical in (0, 1)", name="ck_component_statuses_critical_bool"),
        sa.CheckConstraint(
            "priority_eligible is null or priority_eligible in (0, 1)",
            name="ck_component_statuses_priority_eligible_bool",
        ),
        sa.CheckConstraint(
            "ready_date_type in ('CONFIRMED', 'EXPECTED', 'TENTATIVE')",
            name="ck_component_statuses_ready_date_type",
        ),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_component_statuses_planning_run_id"),
        sa.ForeignKeyConstraint(
            ["planning_run_id", "valve_id"],
            ["valves.planning_run_id", "valves.valve_id"],
            name="fk_component_statuses_run_valve",
        ),
        sa.UniqueConstraint("planning_run_id", "valve_id", "component_line_no", name="uq_component_statuses_run_valve_line"),
    )
    op.create_index("ix_component_statuses_run_valve", "component_statuses", ["planning_run_id", "valve_id"])
    op.create_index("ix_component_statuses_run_component", "component_statuses", ["planning_run_id", "component"])

    op.create_table(
        "routing_operations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("component", sa.String(), nullable=False),
        sa.Column("operation_no", sa.Integer(), nullable=False),
        sa.Column("operation_name", sa.String(), nullable=False),
        sa.Column("machine_type", sa.String(), nullable=False),
        sa.Column("alt_machine", sa.String(), nullable=True),
        sa.Column("std_setup_hrs", sa.REAL(), nullable=True),
        sa.Column("std_run_hrs", sa.REAL(), nullable=True),
        sa.Column("std_total_hrs", sa.REAL(), nullable=False),
        sa.Column("subcontract_allowed", sa.Integer(), nullable=False),
        sa.Column("vendor_process", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.CheckConstraint("operation_no > 0", name="ck_routing_operations_operation_no_positive"),
        sa.CheckConstraint("std_setup_hrs is null or std_setup_hrs >= 0", name="ck_routing_operations_setup_nonnegative"),
        sa.CheckConstraint("std_run_hrs is null or std_run_hrs >= 0", name="ck_routing_operations_run_nonnegative"),
        sa.CheckConstraint("std_total_hrs > 0", name="ck_routing_operations_total_positive"),
        sa.CheckConstraint("subcontract_allowed in (0, 1)", name="ck_routing_operations_subcontract_allowed_bool"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_routing_operations_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", "component", "operation_no", name="uq_routing_operations_run_component_operation"),
    )
    op.create_index("ix_routing_operations_run_component", "routing_operations", ["planning_run_id", "component"])
    op.create_index("ix_routing_operations_run_machine_type", "routing_operations", ["planning_run_id", "machine_type"])
    op.create_index("ix_routing_operations_run_vendor_process", "routing_operations", ["planning_run_id", "vendor_process"])

    op.create_table(
        "machines",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("machine_id", sa.String(), nullable=False),
        sa.Column("machine_type", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("hours_per_day", sa.REAL(), nullable=False),
        sa.Column("efficiency_percent", sa.REAL(), nullable=False),
        sa.Column("effective_hours_day", sa.REAL(), nullable=False),
        sa.Column("shift_pattern", sa.String(), nullable=True),
        sa.Column("buffer_days", sa.REAL(), nullable=False),
        sa.Column("capability_notes", sa.String(), nullable=True),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.CheckConstraint("hours_per_day > 0", name="ck_machines_hours_per_day_positive"),
        sa.CheckConstraint("efficiency_percent > 0 and efficiency_percent <= 100", name="ck_machines_efficiency_range"),
        sa.CheckConstraint("effective_hours_day > 0", name="ck_machines_effective_hours_day_positive"),
        sa.CheckConstraint("buffer_days > 0", name="ck_machines_buffer_days_positive"),
        sa.CheckConstraint("active in (0, 1)", name="ck_machines_active_bool"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_machines_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", "machine_id", name="uq_machines_run_machine_id"),
    )
    op.create_index("ix_machines_run_machine_type", "machines", ["planning_run_id", "machine_type"])
    op.create_index("ix_machines_run_active", "machines", ["planning_run_id", "active"])

    op.create_table(
        "vendors",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("planning_run_id", sa.String(), nullable=False),
        sa.Column("vendor_id", sa.String(), nullable=False),
        sa.Column("vendor_name", sa.String(), nullable=False),
        sa.Column("primary_process", sa.String(), nullable=False),
        sa.Column("turnaround_days", sa.REAL(), nullable=False),
        sa.Column("transport_days_total", sa.REAL(), nullable=False),
        sa.Column("effective_lead_days", sa.REAL(), nullable=False),
        sa.Column("capacity_rating", sa.String(), nullable=True),
        sa.Column("reliability", sa.String(), nullable=True),
        sa.Column("approved", sa.Integer(), nullable=False),
        sa.Column("comments", sa.String(), nullable=True),
        sa.CheckConstraint("turnaround_days >= 0", name="ck_vendors_turnaround_nonnegative"),
        sa.CheckConstraint("transport_days_total >= 0", name="ck_vendors_transport_nonnegative"),
        sa.CheckConstraint("effective_lead_days >= 0", name="ck_vendors_effective_lead_nonnegative"),
        sa.CheckConstraint("approved in (0, 1)", name="ck_vendors_approved_bool"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], name="fk_vendors_planning_run_id"),
        sa.UniqueConstraint("planning_run_id", "vendor_id", name="uq_vendors_run_vendor_id"),
    )
    op.create_index("ix_vendors_run_primary_process", "vendors", ["planning_run_id", "primary_process"])
    op.create_index("ix_vendors_run_approved", "vendors", ["planning_run_id", "approved"])


def downgrade() -> None:
    op.drop_index("ix_vendors_run_approved", table_name="vendors")
    op.drop_index("ix_vendors_run_primary_process", table_name="vendors")
    op.drop_table("vendors")
    op.drop_index("ix_machines_run_active", table_name="machines")
    op.drop_index("ix_machines_run_machine_type", table_name="machines")
    op.drop_table("machines")
    op.drop_index("ix_routing_operations_run_vendor_process", table_name="routing_operations")
    op.drop_index("ix_routing_operations_run_machine_type", table_name="routing_operations")
    op.drop_index("ix_routing_operations_run_component", table_name="routing_operations")
    op.drop_table("routing_operations")
    op.drop_index("ix_component_statuses_run_component", table_name="component_statuses")
    op.drop_index("ix_component_statuses_run_valve", table_name="component_statuses")
    op.drop_table("component_statuses")
    op.drop_index("ix_valves_run_priority", table_name="valves")
    op.drop_index("ix_valves_run_customer", table_name="valves")
    op.drop_index("ix_valves_run_dispatch_date", table_name="valves")
    op.drop_index("ix_valves_run_assembly_date", table_name="valves")
    op.drop_table("valves")
    op.drop_table("master_data_versions")
    op.drop_table("planning_snapshots")
    op.drop_index("ix_planning_runs_planning_start_date", table_name="planning_runs")
    op.drop_index("ix_planning_runs_status", table_name="planning_runs")
    op.drop_index("ix_planning_runs_created_at", table_name="planning_runs")
    op.drop_index("ix_planning_runs_upload_batch_id", table_name="planning_runs")
    op.drop_table("planning_runs")
    op.drop_index("ix_import_validation_issues_issue_code", table_name="import_validation_issues")
    op.drop_index("ix_import_validation_issues_upload_sheet_row", table_name="import_validation_issues")
    op.drop_index("ix_import_validation_issues_upload_severity", table_name="import_validation_issues")
    op.drop_table("import_validation_issues")
    op.drop_index("ix_import_staging_rows_upload_sheet_row", table_name="import_staging_rows")
    op.drop_index("ix_import_staging_rows_upload_sheet", table_name="import_staging_rows")
    op.drop_table("import_staging_rows")
    op.drop_table("raw_upload_artifacts")
    op.drop_index("ix_upload_batches_file_hash", table_name="upload_batches")
    op.drop_index("ix_upload_batches_status", table_name="upload_batches")
    op.drop_index("ix_upload_batches_uploaded_by_user_id", table_name="upload_batches")
    op.drop_index("ix_upload_batches_uploaded_at", table_name="upload_batches")
    op.drop_table("upload_batches")
    op.drop_index("ix_users_active", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")
