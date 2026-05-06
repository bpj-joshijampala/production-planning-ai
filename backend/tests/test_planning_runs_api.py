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
from app.models.canonical import ComponentStatus, Machine, RoutingOperation, Valve, Vendor
from app.models.planning_run import MasterDataVersion, PlanningRun, PlanningSnapshot
from app.models.upload import ImportStagingRow, UploadBatch
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
        master_data_version = session.scalar(
            select(MasterDataVersion).where(MasterDataVersion.planning_run_id == planning_run_id)
        )
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
    assert master_data_version is not None
    assert len(master_data_version.routing_version_hash) == 64
    assert len(master_data_version.machine_version_hash) == 64
    assert len(master_data_version.vendor_version_hash) == 64

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


def test_create_planning_run_allows_missing_routing_warning_only_upload(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Routing_Master"] = [sheets["Routing_Master"][0]]
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
    assert upload_payload["validation_error_count"] == 0
    assert response.status_code == 201
    assert response.json()["canonical_counts"]["routing_operations"] == 0


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


def test_create_planning_run_rolls_back_planning_run_and_canonical_rows_when_promotion_fails(
    client: TestClient,
) -> None:
    upload_payload = _upload_workbook(client, workbook_bytes())
    upload_id = str(upload_payload["id"])

    session_factory = create_session_factory()
    with session_factory() as session:
        valve_row = session.scalar(
            select(ImportStagingRow)
            .where(ImportStagingRow.upload_batch_id == upload_id)
            .where(ImportStagingRow.sheet_name == "Valve_Plan")
        )
        assert valve_row is not None
        session.add(
            ImportStagingRow(
                id="duplicate-staging-valve-for-api",
                upload_batch_id=upload_id,
                sheet_name="Valve_Plan",
                row_number=99,
                normalized_payload_json=valve_row.normalized_payload_json,
                row_hash=valve_row.row_hash,
                created_at=valve_row.created_at,
            )
        )
        session.commit()

    response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_id,
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "PROMOTION_INTEGRITY_ERROR",
        "message": "Canonical promotion violated database constraints. Re-run validation or inspect staged rows.",
    }

    with session_factory() as session:
        upload = session.get(UploadBatch, upload_id)
        planning_run_count = session.scalar(select(func.count()).select_from(PlanningRun))
        valve_count = session.scalar(select(func.count()).select_from(Valve))
        component_count = session.scalar(select(func.count()).select_from(ComponentStatus))
        routing_count = session.scalar(select(func.count()).select_from(RoutingOperation))
        machine_count = session.scalar(select(func.count()).select_from(Machine))
        vendor_count = session.scalar(select(func.count()).select_from(Vendor))
        snapshot_count = session.scalar(select(func.count()).select_from(PlanningSnapshot))

    assert upload is not None
    assert upload.status == "VALIDATED"
    assert planning_run_count == 0
    assert valve_count == 0
    assert component_count == 0
    assert routing_count == 0
    assert machine_count == 0
    assert vendor_count == 0
    assert snapshot_count == 0


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


def test_calculate_get_and_list_planning_runs_endpoints(client: TestClient) -> None:
    first_upload_id = _upload_workbook(client, workbook_bytes())["id"]
    second_upload_id = _upload_workbook(client, workbook_bytes(sheets=_second_workbook_rows()))["id"]
    third_upload_id = _upload_workbook(client, workbook_bytes(sheets=_third_workbook_rows()))["id"]

    first_run = client.post(
        "/api/v1/planning-runs",
        json={"upload_batch_id": first_upload_id, "planning_start_date": "2026-04-21", "planning_horizon_days": 7},
    )
    second_run = client.post(
        "/api/v1/planning-runs",
        json={"upload_batch_id": second_upload_id, "planning_start_date": "2026-04-22", "planning_horizon_days": 14},
    )
    third_run = client.post(
        "/api/v1/planning-runs",
        json={"upload_batch_id": third_upload_id, "planning_start_date": "2026-04-23", "planning_horizon_days": 7},
    )

    assert first_run.status_code == 201
    assert second_run.status_code == 201
    assert third_run.status_code == 201

    calculate_response = client.post(f"/api/v1/planning-runs/{second_run.json()['id']}/calculate")
    assert calculate_response.status_code == 200
    assert calculate_response.json()["status"] == "CALCULATED"
    assert calculate_response.json()["calculated_at"] is not None

    detail_response = client.get(f"/api/v1/planning-runs/{second_run.json()['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == second_run.json()["id"]
    assert detail_response.json()["planning_horizon_days"] == 14
    assert detail_response.json()["canonical_counts"]["valves"] == 1

    list_response = client.get("/api/v1/planning-runs")
    assert list_response.status_code == 200
    assert [row["id"] for row in list_response.json()["items"]] == [
        third_run.json()["id"],
        second_run.json()["id"],
        first_run.json()["id"],
    ]

    latest_default = client.get("/api/v1/planning-runs", params={"latest_only": "true"})
    assert latest_default.status_code == 200
    latest_default_payload = latest_default.json()
    assert latest_default_payload["total"] == 1
    assert latest_default_payload["page_size"] == 1
    assert [row["id"] for row in latest_default_payload["items"]] == [second_run.json()["id"]]

    latest_calculated = client.get("/api/v1/planning-runs", params={"status": "CALCULATED", "latest_only": "true"})
    assert latest_calculated.status_code == 200
    payload = latest_calculated.json()
    assert payload["total"] == 1
    assert payload["page_size"] == 1
    assert [row["id"] for row in payload["items"]] == [second_run.json()["id"]]


def _upload_workbook(client: TestClient, content: bytes) -> dict[str, object]:
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 201
    return response.json()


def _second_workbook_rows() -> dict[str, list[list[object]]]:
    rows = minimal_workbook_rows()
    rows["Valve_Plan"][1] = ["V-200", "O-200", "Beta", "2026-05-02", "2026-04-29", 2.0]
    rows["Component_Status"][1] = ["V-200", "Body", 1, "Y", "N", "2026-04-25", "Y"]
    return rows


def _third_workbook_rows() -> dict[str, list[list[object]]]:
    rows = minimal_workbook_rows()
    rows["Valve_Plan"][1] = ["V-300", "O-300", "Gamma", "2026-05-03", "2026-04-30", 0.8]
    rows["Component_Status"][1] = ["V-300", "Body", 1, "N", "Y", "2026-04-23", "Y"]
    return rows
