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
    database_path = tmp_path / "m2_readiness_schema.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    return database_path


def connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def insert_upload(connection: sqlite3.Connection) -> None:
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


def insert_run_and_valve(connection: sqlite3.Connection) -> None:
    insert_upload(connection)
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
        insert into valves (
            id, planning_run_id, valve_id, order_id, customer, dispatch_date, assembly_date, value_cr
        )
        values ('valve-2', ?, 'V-101', 'O-101', 'Beta', '2026-05-02', '2026-04-29', 0.95)
        """,
        (RUN_ID,),
    )


def test_readiness_migration_creates_valve_readiness_summary_table(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'valve_readiness_summaries'"
        ).fetchone()

    assert table == ("valve_readiness_summaries",)


def test_valve_readiness_summary_constraints_enforce_uniqueness_and_status(migrated_db: Path) -> None:
    with connect(migrated_db) as connection:
        insert_run_and_valve(connection)
        connection.execute(
            """
            insert into valve_readiness_summaries (
                id, planning_run_id, valve_id, customer, assembly_date, dispatch_date, value_cr,
                total_components, ready_components, required_components, ready_required_count, pending_required_count,
                full_kit_flag, near_ready_flag, valve_expected_completion_offset_days, valve_expected_completion_date,
                otd_delay_days, otd_risk_flag, readiness_status, risk_reason, valve_flow_gap_days, valve_flow_imbalance_flag
            )
            values (
                'summary-1', ?, 'V-100', 'Acme', '2026-04-28', '2026-05-01', 1.25,
                2, 1, 2, 1, 1, 0, 1, 2, '2026-04-23', 0, 0, 'NEAR_READY', 'Missing component', null, 0
            )
            """,
            (RUN_ID,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into valve_readiness_summaries (
                    id, planning_run_id, valve_id, customer, assembly_date, dispatch_date, value_cr,
                    total_components, ready_components, required_components, ready_required_count, pending_required_count,
                    full_kit_flag, near_ready_flag, otd_delay_days, otd_risk_flag, readiness_status, valve_flow_imbalance_flag
                )
                values (
                    'summary-2', ?, 'V-100', 'Acme', '2026-04-28', '2026-05-01', 1.25,
                    2, 2, 2, 2, 0, 1, 0, 0, 0, 'READY', 0
                )
                """,
                (RUN_ID,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                insert into valve_readiness_summaries (
                    id, planning_run_id, valve_id, customer, assembly_date, dispatch_date, value_cr,
                    total_components, ready_components, required_components, ready_required_count, pending_required_count,
                    full_kit_flag, near_ready_flag, otd_delay_days, otd_risk_flag, readiness_status, valve_flow_imbalance_flag
                )
                values (
                    'summary-3', ?, 'V-101', 'Beta', '2026-04-29', '2026-05-02', 0.95,
                    1, 1, 1, 1, 0, 1, 0, 0, 0, 'SOMETHING_ELSE', 0
                )
                """,
                (RUN_ID,),
            )
