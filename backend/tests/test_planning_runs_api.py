import json
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.canonical import Machine, Valve, Vendor
from app.models.planning_run import PlanningRun, PlanningSnapshot
from app.models.upload import UploadBatch
from tests.workbook_fixtures import minimal_workbook_rows, workbook_bytes


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "planning_runs_api.sqlite3"
    upload_dir = tmp_path / "uploads"
    export_dir = tmp_path / "exports"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", upload_dir.as_posix())
    monkeypatch.setenv("EXPORT_DIR", export_dir.as_posix())
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()


def test_create_planning_run_promotes_canonical_data_and_stores_snapshot(client: TestClient) -> None:
    upload_id = _upload_workbook(client, workbook_bytes())["id"]

    response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_id,
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 14,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    planning_run_id = payload["id"]
    assert payload["upload_batch_id"] == upload_id
    assert payload["planning_start_date"] == "2026-04-21"
    assert payload["planning_horizon_days"] == 14
    assert payload["status"] == "CREATED"
    assert payload["snapshot_id"]
    assert payload["canonical_counts"] == {
        "valves": 1,
        "component_statuses": 1,
        "routing_operations": 1,
        "machines": 1,
        "vendors": 1,
    }

    session_factory = create_session_factory()
    with session_factory() as session:
        upload = session.get(UploadBatch, upload_id)
        planning_run = session.get(PlanningRun, planning_run_id)
        snapshot = session.scalar(select(PlanningSnapshot).where(PlanningSnapshot.planning_run_id == planning_run_id))
        valve_count = session.scalar(select(func.count()).select_from(Valve).where(Valve.planning_run_id == planning_run_id))
        machine = session.scalar(select(Machine).where(Machine.planning_run_id == planning_run_id))
        vendor = session.scalar(select(Vendor).where(Vendor.planning_run_id == planning_run_id))

    assert upload is not None
    assert upload.status == "PROMOTED"
    assert planning_run is not None
    assert planning_run.status == "CREATED"
    assert valve_count == 1
    assert machine is not None
    assert machine.effective_hours_day == pytest.approx(12.8)
    assert vendor is not None
    assert vendor.effective_lead_days == pytest.approx(4)
    assert snapshot is not None

    snapshot_payload = json.loads(snapshot.snapshot_json)
    assert snapshot_payload["schema_version"] == 1
    assert snapshot_payload["planning_run"]["id"] == planning_run_id
    assert snapshot_payload["planning_run"]["planning_horizon_days"] == 14
    assert snapshot_payload["row_counts"]["valves"] == 1
    assert snapshot_payload["canonical"]["valves"][0]["valve_id"] == "V-100"
    assert snapshot_payload["canonical"]["machines"][0]["effective_hours_day"] == pytest.approx(12.8)


def test_create_planning_run_defaults_to_seven_day_horizon(client: TestClient) -> None:
    upload_id = _upload_workbook(client, workbook_bytes())["id"]

    response = client.post(
        "/api/v1/planning-runs",
        json={"upload_batch_id": upload_id, "planning_start_date": "2026-04-21"},
    )

    assert response.status_code == 201
    assert response.json()["planning_horizon_days"] == 7


def test_create_planning_run_defaults_start_date_to_upload_date(client: TestClient) -> None:
    upload_payload = _upload_workbook(client, workbook_bytes())

    response = client.post("/api/v1/planning-runs", json={"upload_batch_id": upload_payload["id"]})

    assert response.status_code == 201
    assert response.json()["planning_start_date"] == str(upload_payload["uploaded_at"])[:10]
    assert response.json()["planning_horizon_days"] == 7


def test_create_planning_run_allows_warning_only_upload(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Vendor_Master"][1][5] = "N"
    upload_payload = _upload_workbook(client, workbook_bytes(sheets=sheets))

    response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_payload["id"],
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )

    assert upload_payload["validation_warning_count"] == 1
    assert response.status_code == 201
    assert response.json()["canonical_counts"]["vendors"] == 1


def test_create_planning_run_rejects_upload_with_blocking_validation_issues(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    del sheets["Machine_Master"]
    upload_payload = _upload_workbook(client, workbook_bytes(sheets=sheets))

    response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_payload["id"],
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )

    assert upload_payload["status"] == "VALIDATION_FAILED"
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VALIDATION_BLOCKED"

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_run_count = session.scalar(select(func.count()).select_from(PlanningRun))

    assert planning_run_count == 0


def test_create_planning_run_rejects_duplicate_key_upload_without_server_error(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Valve_Plan"].append(["V-100", "O-101", "Acme 2", "2026-05-02", "2026-04-29", 2.0])
    upload_payload = _upload_workbook(client, workbook_bytes(sheets=sheets))

    response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_payload["id"],
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )

    assert upload_payload["status"] == "VALIDATION_FAILED"
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "VALIDATION_BLOCKED"


def test_create_planning_run_rejects_missing_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": "missing-upload",
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "UPLOAD_NOT_FOUND"


def test_create_planning_run_rejects_invalid_horizon(client: TestClient) -> None:
    upload_id = _upload_workbook(client, workbook_bytes())["id"]

    response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_id,
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 30,
        },
    )

    assert response.status_code == 422


def _upload_workbook(client: TestClient, content: bytes) -> dict[str, object]:
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 201
    return response.json()
