from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.core.auth import DEFAULT_DEV_USER_ID
from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import PlannerOverride, Recommendation, ReportExport
from app.models.planning_run import PlanningRun
from app.models.upload import UploadBatch
from app.models.user import User
from tests.workbook_fixtures import workbook_bytes


@pytest.fixture(name="client")
def fixture_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "m5_security_audit.sqlite3"
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


def test_default_planner_user_is_used_for_upload_run_override_and_export_audit(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["id"]

    planning_run_response = client.post(
        "/api/v1/planning-runs",
        json={"upload_batch_id": upload_id, "planning_start_date": "2026-04-21", "planning_horizon_days": 7},
    )
    assert planning_run_response.status_code == 201
    planning_run_id = planning_run_response.json()["id"]

    calculate_response = client.post(f"/api/v1/planning-runs/{planning_run_id}/calculate")
    assert calculate_response.status_code == 200

    recommendation_id = _first_recommendation_id(planning_run_id)
    override_response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation_id,
            "override_decision": "ACCEPT",
            "reason": "Audit trail acceptance",
            "remarks": "M5-E5 audit coverage",
        },
    )
    assert override_response.status_code == 201
    assert override_response.json()["user_id"] == DEFAULT_DEV_USER_ID
    assert override_response.json()["user_display_name"] == "Development Planner"

    export_response = client.post(
        f"/api/v1/planning-runs/{planning_run_id}/exports",
        json={"report_type": "MACHINE_LOAD", "file_format": "XLSX"},
    )
    assert export_response.status_code == 201
    export_path = Path(export_response.json()["file_path"])

    session_factory = create_session_factory()
    with session_factory() as session:
        user = session.get(User, DEFAULT_DEV_USER_ID)
        upload = session.get(UploadBatch, upload_id)
        planning_run = session.get(PlanningRun, planning_run_id)
        override = session.scalar(select(PlannerOverride).where(PlannerOverride.planning_run_id == planning_run_id))
        report_export = session.scalar(select(ReportExport).where(ReportExport.planning_run_id == planning_run_id))

    assert user is not None
    assert user.username == "dev.planner"
    assert user.display_name == "Development Planner"
    assert user.role == "PLANNER"
    assert user.active == 1

    assert upload is not None
    assert upload.uploaded_by_user_id == DEFAULT_DEV_USER_ID
    assert upload.uploaded_at

    assert planning_run is not None
    assert planning_run.created_by_user_id == DEFAULT_DEV_USER_ID
    assert planning_run.created_at
    assert planning_run.calculated_at

    assert override is not None
    assert override.user_id == DEFAULT_DEV_USER_ID
    assert override.created_at
    assert override.original_recommendation is not None
    assert override.override_decision == "ACCEPT"
    assert override.reason == "Audit trail acceptance"

    assert report_export is not None
    assert report_export.generated_by_user_id == DEFAULT_DEV_USER_ID
    assert report_export.generated_at
    assert report_export.report_type == "MACHINE_LOAD"
    assert report_export.file_path == str(export_path)
    assert export_path.exists()


@pytest.mark.parametrize("filename", ["plan.xls", "plan.xlsm", "plan.csv", "plan.tsv", "plan.txt"])
def test_upload_rejects_unsupported_file_types_before_creating_audit_rows(
    client: TestClient,
    filename: str,
) -> None:
    response = client.post(
        "/api/v1/uploads",
        files={"file": (filename, b"not an xlsx workbook", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"

    session_factory = create_session_factory()
    with session_factory() as session:
        upload_count = session.scalar(select(func.count()).select_from(UploadBatch))

    assert upload_count == 0


def test_non_writer_role_can_export_but_cannot_upload(client: TestClient) -> None:
    planning_run_id = _create_calculated_planning_run(client)
    _set_default_user(role="HOD", active=1)

    export_response = client.post(
        f"/api/v1/planning-runs/{planning_run_id}/exports",
        json={"report_type": "MACHINE_LOAD", "file_format": "XLSX"},
    )
    blocked_upload_response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                "another-plan.xlsx",
                workbook_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert export_response.status_code == 201
    assert export_response.json()["generated_by_user_id"] == DEFAULT_DEV_USER_ID
    assert blocked_upload_response.status_code == 403
    assert blocked_upload_response.json()["detail"] == {
        "code": "ROLE_NOT_ALLOWED",
        "message": "Role HOD is not allowed to perform this action.",
    }


def test_inactive_default_user_cannot_create_audit_rows(client: TestClient) -> None:
    _set_default_user(role="PLANNER", active=0)

    response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "ACTING_USER_INACTIVE",
        "message": "Acting user is inactive and cannot perform this action.",
    }

    session_factory = create_session_factory()
    with session_factory() as session:
        upload_count = session.scalar(select(func.count()).select_from(UploadBatch))

    assert upload_count == 0


def _create_calculated_planning_run(client: TestClient) -> str:
    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("plan.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert upload_response.status_code == 201

    planning_run_response = client.post(
        "/api/v1/planning-runs",
        json={
            "upload_batch_id": upload_response.json()["id"],
            "planning_start_date": "2026-04-21",
            "planning_horizon_days": 7,
        },
    )
    assert planning_run_response.status_code == 201
    planning_run_id = planning_run_response.json()["id"]

    calculate_response = client.post(f"/api/v1/planning-runs/{planning_run_id}/calculate")
    assert calculate_response.status_code == 200
    return planning_run_id


def _first_recommendation_id(planning_run_id: str) -> str:
    session_factory = create_session_factory()
    with session_factory() as session:
        recommendation = session.scalar(
            select(Recommendation)
            .where(Recommendation.planning_run_id == planning_run_id)
            .order_by(Recommendation.id.asc())
        )
    assert recommendation is not None
    return recommendation.id


def _set_default_user(*, role: str, active: int) -> None:
    session_factory = create_session_factory()
    with session_factory() as session:
        user = session.get(User, DEFAULT_DEV_USER_ID)
        assert user is not None
        user.role = role
        user.active = active
        session.commit()
