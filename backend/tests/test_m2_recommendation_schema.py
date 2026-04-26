import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
UPLOAD_ID = "10000000-0000-0000-0000-000000000001"
RUN_ID = "20000000-0000-0000-0000-000000000001"


@pytest.fixture()
def migrated_db(tmp_path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "m2_recommendation_schema.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    return database_path


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def insert_run_fixture(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        insert into upload_batches (
            id, original_filename, stored_filename, file_hash, file_size_bytes,
            uploaded_by_user_id, uploaded_at, status, validation_error_count, validation_warning_count
        )
        values (?, 'plan.xlsx', 'stored.xlsx', 'abc123', 1234, ?, '2026-04-21T00:00:00Z', 'PROMOTED', 0, 0)
        """,
        (UPLOAD_ID, DEV_USER_ID),
    )
    connection.execute(
        """
        insert into planning_runs (
            id, upload_batch_id, planning_start_date, planning_horizon_days,
            status, created_by_user_id, created_at
        )
        values (?, ?, '2026-04-21', 7, 'CREATED', ?, '2026-04-21T00:00:00Z')
        """,
        (RUN_ID, UPLOAD_ID, DEV_USER_ID),
    )
    connection.execute(
        """
        insert into vendors (
            id, planning_run_id, vendor_id, vendor_name, primary_process,
            turnaround_days, transport_days_total, effective_lead_days, capacity_rating,
            reliability, approved, comments
        )
        values (
            'vendor-1', ?, 'VEN-1', 'Vendor One', 'HBM',
            3, 1, 4, 'Medium', 'A', 1, null
        )
        """,
        (RUN_ID,),
    )


def test_recommendation_and_vendor_load_migrations_create_tables(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        recommendations = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'recommendations'"
        ).fetchone()
        vendor_load = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'vendor_load_summaries'"
        ).fetchone()

    assert recommendations == ("recommendations",)
    assert vendor_load == ("vendor_load_summaries",)


def test_recommendation_and_vendor_load_schema_enforce_constraints(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_fixture(connection)
        connection.execute(
            """
            insert into vendor_load_summaries (
                id, planning_run_id, vendor_id, vendor_name, primary_process,
                vendor_recommended_jobs, max_recommended_jobs_per_horizon,
                selected_vendor_overloaded_flag, status
            )
            values (
                'vendor-load-1', ?, 'VEN-1', 'Vendor One', 'HBM',
                0, 3, 0, 'OK'
            )
            """,
            (RUN_ID,),
        )
        connection.execute(
            """
            insert into recommendations (
                id, planning_run_id, planned_operation_id, recommendation_type,
                valve_id, component_line_no, component, operation_name, machine_type,
                suggested_machine_type, suggested_vendor_id, suggested_vendor_name,
                internal_wait_days, processing_time_days, internal_completion_days,
                vendor_total_days, vendor_gain_days, subcontract_batch_candidate_count,
                batch_subcontract_opportunity_flag, reason_codes_json, explanation, status, created_at
            )
            values (
                'rec-1', ?, null, 'OK_INTERNAL',
                'V-100', 1, 'Body', 'HBM roughing', 'HBM',
                null, null, null,
                0, 1, 1,
                null, null, null,
                0, '[\"OK_INTERNAL\"]', 'OK placeholder.', 'PENDING', '2026-04-26T00:00:00Z'
            )
            """,
            (RUN_ID,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into recommendations (
                    id, planning_run_id, planned_operation_id, recommendation_type,
                    valve_id, component_line_no, component, operation_name, machine_type,
                    suggested_machine_type, suggested_vendor_id, suggested_vendor_name,
                    internal_wait_days, processing_time_days, internal_completion_days,
                    vendor_total_days, vendor_gain_days, subcontract_batch_candidate_count,
                    batch_subcontract_opportunity_flag, reason_codes_json, explanation, status, created_at
                )
                values (
                    'rec-2', ?, null, 'NOT_REAL',
                    null, null, null, null, null,
                    null, null, null,
                    null, null, null,
                    null, null, null,
                    0, '[]', 'Bad type.', 'PENDING', '2026-04-26T00:00:00Z'
                )
                """,
                (RUN_ID,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into vendor_load_summaries (
                    id, planning_run_id, vendor_id, vendor_name, primary_process,
                    vendor_recommended_jobs, max_recommended_jobs_per_horizon,
                    selected_vendor_overloaded_flag, status
                )
                values (
                    'vendor-load-2', ?, 'VEN-1', 'Vendor One', 'HBM',
                    -1, 3, 0, 'OK'
                )
                """,
                (RUN_ID,),
            )
