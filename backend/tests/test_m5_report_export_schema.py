import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
UPLOAD_ID = "10000000-0000-0000-0000-000000000011"
RUN_ID = "20000000-0000-0000-0000-000000000011"


@pytest.fixture()
def migrated_db(tmp_path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "m5_report_export_schema.sqlite3"
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
        values (?, 'plan.xlsx', 'stored.xlsx', 'abc123', 1234, ?, '2026-05-01T00:00:00Z', 'CALCULATED', 0, 0)
        """,
        (UPLOAD_ID, DEV_USER_ID),
    )
    connection.execute(
        """
        insert into planning_runs (
            id, upload_batch_id, planning_start_date, planning_horizon_days,
            status, created_by_user_id, created_at, calculated_at
        )
        values (?, ?, '2026-05-01', 7, 'CALCULATED', ?, '2026-05-01T00:00:00Z', '2026-05-01T00:05:00Z')
        """,
        (RUN_ID, UPLOAD_ID, DEV_USER_ID),
    )


def test_report_exports_migration_creates_table(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        row = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'report_exports'"
        ).fetchone()

    assert row == ("report_exports",)


def test_report_exports_schema_enforces_constraints(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_fixture(connection)
        connection.execute(
            """
            insert into report_exports (
                id, planning_run_id, report_type, file_path, file_format,
                generated_by_user_id, generated_at, metadata_json
            )
            values (
                'export-1', ?, 'MACHINE_LOAD', 'C:/tmp/machine_load.xlsx', 'XLSX',
                ?, '2026-05-01T00:10:00Z', '{"sheet_names":["Machine_Load"]}'
            )
            """,
            (RUN_ID, DEV_USER_ID),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into report_exports (
                    id, planning_run_id, report_type, file_path, file_format,
                    generated_by_user_id, generated_at, metadata_json
                )
                values (
                    'export-2', ?, 'NOT_REAL', 'C:/tmp/invalid.xlsx', 'XLSX',
                    ?, '2026-05-01T00:11:00Z', null
                )
                """,
                (RUN_ID, DEV_USER_ID),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into report_exports (
                    id, planning_run_id, report_type, file_path, file_format,
                    generated_by_user_id, generated_at, metadata_json
                )
                values (
                    'export-4', ?, 'MACHINE_LOAD', 'C:/tmp/machine_load.pdf', 'PDF',
                    ?, '2026-05-01T00:13:00Z', null
                )
                """,
                (RUN_ID, DEV_USER_ID),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into report_exports (
                    id, planning_run_id, report_type, file_path, file_format,
                    generated_by_user_id, generated_at, metadata_json
                )
                values (
                    'export-3', ?, 'MACHINE_LOAD', '   ', 'TXT',
                    ?, '2026-05-01T00:12:00Z', '{bad-json}'
                )
                """,
                (RUN_ID, DEV_USER_ID),
            )
