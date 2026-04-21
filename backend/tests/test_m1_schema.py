import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings


M1_TABLES = {
    "users",
    "upload_batches",
    "raw_upload_artifacts",
    "import_staging_rows",
    "import_validation_issues",
    "planning_runs",
    "planning_snapshots",
    "master_data_versions",
    "valves",
    "component_statuses",
    "routing_operations",
    "machines",
    "vendors",
}

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
UPLOAD_ID = "10000000-0000-0000-0000-000000000001"
RUN_ID = "20000000-0000-0000-0000-000000000001"


@pytest.fixture()
def migrated_db(tmp_path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "m1_schema.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    return database_path


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
    }


def insert_upload(connection: sqlite3.Connection, upload_id: str = UPLOAD_ID) -> None:
    connection.execute(
        """
        insert into upload_batches (
            id, original_filename, stored_filename, file_hash, file_size_bytes,
            uploaded_by_user_id, uploaded_at, status, validation_error_count,
            validation_warning_count
        )
        values (?, 'plan.xlsx', 'stored.xlsx', 'abc123', 1234, ?, '2026-04-21T00:00:00Z', 'UPLOADED', 0, 0)
        """,
        (upload_id, DEV_USER_ID),
    )


def insert_planning_run(connection: sqlite3.Connection, run_id: str = RUN_ID, upload_id: str = UPLOAD_ID) -> None:
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


def insert_valve(connection: sqlite3.Connection, run_id: str = RUN_ID, valve_id: str = "V-100") -> None:
    row_id = f"valve-{run_id[-1]}-{valve_id}"
    connection.execute(
        """
        insert into valves (
            id, planning_run_id, valve_id, order_id, customer, dispatch_date,
            assembly_date, value_cr
        )
        values (?, ?, ?, 'O-100', 'Acme', '2026-05-01', '2026-04-28', 1.25)
        """,
        (row_id, run_id, valve_id),
    )


def test_m1_migration_creates_required_tables_and_seed_user(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        assert M1_TABLES.issubset(table_names(connection))

        seeded_user = connection.execute(
            "select username, display_name, role, active from users where id = ?",
            (DEV_USER_ID,),
        ).fetchone()
        assert seeded_user == ("dev.planner", "Development Planner", "PLANNER", 1)


def test_upload_batch_requires_existing_user(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into upload_batches (
                    id, original_filename, stored_filename, file_hash, file_size_bytes,
                    uploaded_by_user_id, uploaded_at, status, validation_error_count,
                    validation_warning_count
                )
                values ('bad-upload', 'plan.xlsx', 'stored.xlsx', 'abc123', 1234, 'missing-user',
                    '2026-04-21T00:00:00Z', 'UPLOADED', 0, 0)
                """
            )


def test_boolean_and_enum_checks_reject_invalid_values(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into users (id, username, display_name, role, active, created_at)
                values ('bad-active', 'bad.active', 'Bad Active', 'PLANNER', 2, '2026-04-21T00:00:00Z')
                """
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into users (id, username, display_name, role, active, created_at)
                values ('bad-role', 'bad.role', 'Bad Role', 'SUPERVISOR', 1, '2026-04-21T00:00:00Z')
                """
            )


def test_planning_horizon_check_rejects_invalid_horizon(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_upload(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into planning_runs (
                    id, upload_batch_id, planning_start_date, planning_horizon_days,
                    status, created_by_user_id, created_at
                )
                values ('bad-run', ?, '2026-04-21', 30, 'CREATED', ?, '2026-04-21T00:00:00Z')
                """,
                (UPLOAD_ID, DEV_USER_ID),
            )


def test_run_scoped_valve_uniqueness(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_upload(connection)
        insert_planning_run(connection)
        insert_valve(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into valves (
                    id, planning_run_id, valve_id, order_id, customer, dispatch_date,
                    assembly_date, value_cr
                )
                values ('duplicate-valve', ?, 'V-100', 'O-101', 'Acme', '2026-05-01', '2026-04-28', 1.25)
                """,
                (RUN_ID,),
            )

        second_upload_id = "10000000-0000-0000-0000-000000000002"
        second_run_id = "20000000-0000-0000-0000-000000000002"
        insert_upload(connection, second_upload_id)
        insert_planning_run(connection, second_run_id, second_upload_id)
        insert_valve(connection, second_run_id, "V-100")


def test_component_line_uniqueness_allows_repeated_component_names(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_upload(connection)
        insert_planning_run(connection)
        insert_valve(connection)

        for line_no in (1, 2):
            connection.execute(
                """
                insert into component_statuses (
                    id, planning_run_id, valve_id, component_line_no, component, qty,
                    fabrication_required, fabrication_complete, expected_ready_date,
                    critical, ready_date_type
                )
                values (?, ?, 'V-100', ?, 'Body', 1, 1, 0, '2026-04-25', 1, 'EXPECTED')
                """,
                (f"component-{line_no}", RUN_ID, line_no),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into component_statuses (
                    id, planning_run_id, valve_id, component_line_no, component, qty,
                    fabrication_required, fabrication_complete, expected_ready_date,
                    critical, ready_date_type
                )
                values ('component-duplicate', ?, 'V-100', 2, 'Bonnet', 1, 1, 0, '2026-04-25', 1, 'EXPECTED')
                """,
                (RUN_ID,),
            )


def test_json_columns_reject_invalid_json(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_upload(connection)
        insert_planning_run(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into import_staging_rows (
                    id, upload_batch_id, sheet_name, row_number, normalized_payload_json, created_at
                )
                values ('bad-json-staging', ?, 'Valve_Plan', 2, 'not-json', '2026-04-21T00:00:00Z')
                """,
                (UPLOAD_ID,),
            )

        connection.execute(
            """
            insert into planning_snapshots (id, planning_run_id, snapshot_json, created_at)
            values ('snapshot-ok', ?, ?, '2026-04-21T00:00:00Z')
            """,
            (RUN_ID, json.dumps({"row_counts": {"valves": 1}})),
        )
