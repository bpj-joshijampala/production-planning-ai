import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
UPLOAD_ID_1 = "10000000-0000-0000-0000-000000000001"
UPLOAD_ID_2 = "10000000-0000-0000-0000-000000000002"
RUN_ID_1 = "20000000-0000-0000-0000-000000000001"
RUN_ID_2 = "20000000-0000-0000-0000-000000000002"


@pytest.fixture()
def migrated_db(tmp_path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "m2_throughput_schema.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    return database_path


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def insert_run_fixture(connection: sqlite3.Connection, *, upload_id: str, run_id: str) -> None:
    connection.execute(
        """
        insert into upload_batches (
            id, original_filename, stored_filename, file_hash, file_size_bytes,
            uploaded_by_user_id, uploaded_at, status, validation_error_count, validation_warning_count
        )
        values (?, 'plan.xlsx', 'stored.xlsx', 'abc123', 1234, ?, '2026-04-21T00:00:00Z', 'PROMOTED', 0, 0)
        """,
        (upload_id, DEV_USER_ID),
    )
    connection.execute(
        """
        insert into planning_runs (
            id, upload_batch_id, planning_start_date, planning_horizon_days,
            status, created_by_user_id, created_at
        )
        values (?, ?, '2026-04-21', 7, 'CREATED', ?, '2026-04-21T00:00:00Z')
        """,
        (run_id, upload_id, DEV_USER_ID),
    )


def test_throughput_migration_creates_throughput_summaries_table(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        throughput = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'throughput_summaries'"
        ).fetchone()

    assert throughput == ("throughput_summaries",)


def test_throughput_schema_enforces_unique_run_and_metric_constraints(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_fixture(connection, upload_id=UPLOAD_ID_1, run_id=RUN_ID_1)
        insert_run_fixture(connection, upload_id=UPLOAD_ID_2, run_id=RUN_ID_2)

        connection.execute(
            """
            insert into throughput_summaries (
                id, planning_run_id, target_throughput_value_cr,
                planned_throughput_value_cr, throughput_gap_cr, throughput_risk_flag
            )
            values ('throughput-1', ?, 2.5, 1.75, 0.75, 1)
            """,
            (RUN_ID_1,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into throughput_summaries (
                    id, planning_run_id, target_throughput_value_cr,
                    planned_throughput_value_cr, throughput_gap_cr, throughput_risk_flag
                )
                values ('throughput-dup', ?, 2.5, 2.5, 0.0, 0)
                """,
                (RUN_ID_1,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into throughput_summaries (
                    id, planning_run_id, target_throughput_value_cr,
                    planned_throughput_value_cr, throughput_gap_cr, throughput_risk_flag
                )
                values ('throughput-2', ?, 2.5, 1.0, -1.0, 1)
                """,
                (RUN_ID_2,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into throughput_summaries (
                    id, planning_run_id, target_throughput_value_cr,
                    planned_throughput_value_cr, throughput_gap_cr, throughput_risk_flag
                )
                values ('throughput-3', ?, 2.5, 1.0, 1.5, 2)
                """,
                (RUN_ID_2,),
            )
