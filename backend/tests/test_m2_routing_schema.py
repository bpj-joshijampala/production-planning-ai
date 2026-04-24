import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
UPLOAD_ID = "10000000-0000-0000-0000-000000000001"
RUN_ID = "20000000-0000-0000-0000-000000000001"
PLANNED_OPERATION_ID = "30000000-0000-0000-0000-000000000001"


@pytest.fixture()
def migrated_db(tmp_path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "m2_routing_schema.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    return database_path


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def insert_run_component_and_operation_fixture(connection: sqlite3.Connection) -> None:
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
        values ('component-1', ?, 'V-100', 1, 'Body', 1, 1, 1, '2026-04-21', 1, 'CONFIRMED')
        """,
        (RUN_ID,),
    )
    connection.execute(
        """
        insert into planned_operations (
            id, planning_run_id, valve_id, component_line_no, component, operation_no, operation_name,
            machine_type, alt_machine, qty, operation_hours, availability_date, date_confidence, priority_score,
            sort_sequence, availability_offset_days, operation_arrival_offset_days, operation_arrival_date,
            scheduled_start_offset_days, internal_wait_days, processing_time_days, internal_completion_days,
            internal_completion_offset_days, internal_completion_date, extreme_delay_flag, recommendation_status
        )
        values (
            ?, ?, 'V-100', 1, 'Body', 10, 'HBM roughing',
            'HBM', null, 1, 5, '2026-04-21', 'CONFIRMED', 1770,
            1, 0, 0, '2026-04-21',
            0, 0, 0, 0, 0, '2026-04-21', 0, null
        )
        """,
        (PLANNED_OPERATION_ID, RUN_ID),
    )


def test_routing_migration_creates_planned_operations_and_flow_blockers_tables(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        planned_operations = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'planned_operations'"
        ).fetchone()
        flow_blockers = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'flow_blockers'"
        ).fetchone()

    assert planned_operations == ("planned_operations",)
    assert flow_blockers == ("flow_blockers",)


def test_routing_schema_constraints_enforce_operation_and_blocker_enums(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_component_and_operation_fixture(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into planned_operations (
                    id, planning_run_id, valve_id, component_line_no, component, operation_no, operation_name,
                    machine_type, alt_machine, qty, operation_hours, availability_date, date_confidence, priority_score,
                    sort_sequence, availability_offset_days, operation_arrival_offset_days, operation_arrival_date,
                    scheduled_start_offset_days, internal_wait_days, processing_time_days, internal_completion_days,
                    internal_completion_offset_days, internal_completion_date, extreme_delay_flag, recommendation_status
                )
                values (
                    'planned-2', ?, 'V-100', 1, 'Body', 20, 'Finish',
                    'HBM', null, 1, 5, '2026-04-21', 'SOMETHING_ELSE', 1770,
                    2, 0, 0, '2026-04-21',
                    0, 0, 0, 0, 0, '2026-04-21', 0, null
                )
                """,
                (RUN_ID,),
            )

        connection.execute(
            """
            insert into flow_blockers (
                id, planning_run_id, planned_operation_id, valve_id, component_line_no, component,
                operation_name, blocker_type, cause, recommended_action, severity, created_at
            )
            values (
                'blocker-1', ?, ?, 'V-100', 1, 'Body',
                'HBM roughing', 'MISSING_ROUTING', 'Missing route', 'Add routing', 'CRITICAL', '2026-04-21T00:00:00Z'
            )
            """,
            (RUN_ID, PLANNED_OPERATION_ID),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into flow_blockers (
                    id, planning_run_id, planned_operation_id, valve_id, component_line_no, component,
                    operation_name, blocker_type, cause, recommended_action, severity, created_at
                )
                values (
                    'blocker-2', ?, ?, 'V-100', 1, 'Body',
                    'HBM roughing', 'NOT_A_REAL_BLOCKER', 'Bad blocker', 'Do something', 'CRITICAL', '2026-04-21T00:00:00Z'
                )
                """,
                (RUN_ID, PLANNED_OPERATION_ID),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into flow_blockers (
                    id, planning_run_id, planned_operation_id, valve_id, component_line_no, component,
                    operation_name, blocker_type, cause, recommended_action, severity, created_at
                )
                values (
                    'blocker-3', ?, ?, 'V-100', 1, 'Body',
                    'HBM roughing', 'MISSING_ROUTING', 'Bad severity', 'Do something', 'SEVERE', '2026-04-21T00:00:00Z'
                )
                """,
                (RUN_ID, PLANNED_OPERATION_ID),
            )
