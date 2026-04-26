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
    database_path = tmp_path / "m2_planner_override_schema.sqlite3"
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


def test_planner_override_migration_creates_planner_overrides_table(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        planner_overrides = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'planner_overrides'"
        ).fetchone()

    assert planner_overrides == ("planner_overrides",)


def test_planner_override_schema_enforces_required_constraints(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_fixture(connection)
        connection.execute(
            """
            insert into planner_overrides (
                id, planning_run_id, recommendation_id, entity_type, entity_id,
                original_recommendation, override_decision, reason, remarks, stale_flag, user_id, created_at
            )
            values (
                'override-1', ?, null, 'OPERATION', 'operation-123',
                'OK_INTERNAL', 'FORCE_VENDOR', 'Expedite', null, 0, ?, '2026-04-25T00:00:00Z'
            )
            """,
            (RUN_ID, DEV_USER_ID),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into planner_overrides (
                    id, planning_run_id, recommendation_id, entity_type, entity_id,
                    original_recommendation, override_decision, reason, remarks, stale_flag, user_id, created_at
                )
                values (
                    'override-2', ?, null, 'BAD_TYPE', 'entity-1',
                    null, 'FORCE_VENDOR', 'Expedite', null, 0, ?, '2026-04-25T00:00:00Z'
                )
                """,
                (RUN_ID, DEV_USER_ID),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into planner_overrides (
                    id, planning_run_id, recommendation_id, entity_type, entity_id,
                    original_recommendation, override_decision, reason, remarks, stale_flag, user_id, created_at
                )
                values (
                    'override-3', ?, null, 'VALVE', '   ',
                    null, 'HOLD', '   ', null, 0, ?, '2026-04-25T00:00:00Z'
                )
                """,
                (RUN_ID, DEV_USER_ID),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into planner_overrides (
                    id, planning_run_id, recommendation_id, entity_type, entity_id,
                    original_recommendation, override_decision, reason, remarks, stale_flag, user_id, created_at
                )
                values (
                    'override-4', ?, null, 'MACHINE', 'HBM',
                    null, 'REBALANCE', 'Capacity review', null, 2, ?, '2026-04-25T00:00:00Z'
                )
                """,
                (RUN_ID, DEV_USER_ID),
            )
