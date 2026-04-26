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
    database_path = tmp_path / "m2_machine_load_schema.sqlite3"
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


def test_machine_load_migration_creates_machine_load_summaries_table(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        machine_load = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'machine_load_summaries'"
        ).fetchone()

    assert machine_load == ("machine_load_summaries",)


def test_machine_load_schema_enforces_status_and_nonnegative_metrics(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_fixture(connection)
        connection.execute(
            """
                insert into machine_load_summaries (
                    id, planning_run_id, machine_type, total_operation_hours, capacity_hours_per_day,
                    load_days, buffer_days, overload_flag, overload_days, spare_capacity_days,
                    underutilized_flag, batch_risk_flag, status, queue_approximation_warning
                )
                values (
                    'machine-load-1', ?, 'HBM', 16, 8,
                    2, 5, 0, 0, 3,
                    1, 1, 'UNDERUTILIZED', 'Queue is priority-based and aggregated by machine type. Review before execution.'
                )
                """,
                (RUN_ID,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into machine_load_summaries (
                    id, planning_run_id, machine_type, total_operation_hours, capacity_hours_per_day,
                    load_days, buffer_days, overload_flag, overload_days, spare_capacity_days,
                    underutilized_flag, batch_risk_flag, status, queue_approximation_warning
                )
                values (
                    'machine-load-2', ?, 'VTL', 4, 8,
                    -1, 3, 0, 0, 3,
                    1, 0, 'UNDERUTILIZED', 'Queue is priority-based and aggregated by machine type. Review before execution.'
                )
                """,
                (RUN_ID,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into machine_load_summaries (
                    id, planning_run_id, machine_type, total_operation_hours, capacity_hours_per_day,
                    load_days, buffer_days, overload_flag, overload_days, spare_capacity_days,
                    underutilized_flag, batch_risk_flag, status, queue_approximation_warning
                )
                values (
                    'machine-load-3', ?, 'LATHE', 0, 0,
                    0, 0, 0, 0, 0,
                    0, 0, 'NOT_A_REAL_STATUS', 'Queue is priority-based and aggregated by machine type. Review before execution.'
                )
                """,
                (RUN_ID,),
            )
