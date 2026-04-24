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
    database_path = tmp_path / "m2_priority_schema.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    return database_path


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def insert_run_and_component(connection: sqlite3.Connection) -> None:
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
        insert into valves (
            id, planning_run_id, valve_id, order_id, customer, dispatch_date, assembly_date, value_cr
        )
        values ('valve-1', ?, 'V-100', 'O-100', 'Acme', '2026-05-01', '2026-04-28', 1.25)
        """,
        (RUN_ID,),
    )
    connection.execute(
        """
        insert into component_statuses (
            id, planning_run_id, valve_id, component_line_no, component, qty,
            fabrication_required, fabrication_complete, expected_ready_date, critical, ready_date_type
        )
        values ('component-1', ?, 'V-100', 1, 'Body', 1, 1, 0, '2026-04-24', 1, 'EXPECTED')
        """,
        (RUN_ID,),
    )


def test_priority_migration_creates_incoming_load_items_table(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'incoming_load_items'"
        ).fetchone()

    assert table == ("incoming_load_items",)


def test_incoming_load_item_constraints_enforce_uniqueness_confidence_and_json(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_and_component(connection)
        connection.execute(
            """
            insert into incoming_load_items (
                id, planning_run_id, valve_id, component_line_no, component, qty, availability_date,
                date_confidence, current_ready_flag, machine_types_json, priority_score, sort_sequence,
                same_day_arrival_load_days, batch_risk_flag
            )
            values (
                'incoming-1', ?, 'V-100', 1, 'Body', 1, '2026-04-24',
                'EXPECTED', 0, '["HBM"]', 1145, 1, null, 0
            )
            """,
            (RUN_ID,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into incoming_load_items (
                    id, planning_run_id, valve_id, component_line_no, component, qty, availability_date,
                    date_confidence, current_ready_flag, machine_types_json, priority_score, sort_sequence, batch_risk_flag
                )
                values (
                    'incoming-2', ?, 'V-100', 1, 'Body', 1, '2026-04-24',
                    'EXPECTED', 0, '["HBM"]', 1145, 2, 0
                )
                """,
                (RUN_ID,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into incoming_load_items (
                    id, planning_run_id, valve_id, component_line_no, component, qty, availability_date,
                    date_confidence, current_ready_flag, machine_types_json, priority_score, sort_sequence, batch_risk_flag
                )
                values (
                    'incoming-3', ?, 'V-100', 2, 'Body-2', 1, '2026-04-24',
                    'SOMETHING_ELSE', 0, '["HBM"]', 1145, 2, 0
                )
                """,
                (RUN_ID,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into incoming_load_items (
                    id, planning_run_id, valve_id, component_line_no, component, qty, availability_date,
                    date_confidence, current_ready_flag, machine_types_json, priority_score, sort_sequence, batch_risk_flag
                )
                values (
                    'incoming-4', ?, 'V-100', 2, 'Body-2', 1, '2026-04-24',
                    'EXPECTED', 0, 'not-json', 1145, 2, 0
                )
                """,
                (RUN_ID,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into incoming_load_items (
                    id, planning_run_id, valve_id, component_line_no, component, qty, availability_date,
                    date_confidence, current_ready_flag, machine_types_json, priority_score, sort_sequence, batch_risk_flag
                )
                values (
                    'incoming-5', ?, 'V-100', 2, 'Body-2', 1, '2026-04-24',
                    'EXPECTED', 0, '{"machine":"HBM"}', 1145, 2, 0
                )
                """,
                (RUN_ID,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into incoming_load_items (
                    id, planning_run_id, valve_id, component_line_no, component, qty, availability_date,
                    date_confidence, current_ready_flag, machine_types_json, priority_score, sort_sequence, batch_risk_flag
                )
                values (
                    'incoming-6', ?, 'V-100', 2, 'Body-2', 1, '2026-04-24',
                    'EXPECTED', 0, '["HBM"]', 1145, 0, 0
                )
                """,
                (RUN_ID,),
            )
