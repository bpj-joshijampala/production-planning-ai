from collections.abc import Generator
from io import BytesIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.auth import DEFAULT_DEV_USER_ID
from app.core.config import get_settings
from app.db.session import create_session_factory
from app.main import create_app
from app.models.output import PlannerOverride, Recommendation, ReportExport
from app.models.planning_run import PlanningRun
from app.models.upload import UploadBatch
from app.models.user import User
from app.schemas.planner_override import PlannerOverrideCreateRequest
from app.schemas.planning_run import PlanningRunCreateRequest
from app.services.planner_overrides import create_planner_override
from app.services.planning_runs import create_planning_run
from app.services.report_exports import generate_first_build_report_export
from app.services.uploads import create_upload
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
    assert calculate_response.json()["calculated_by_user_id"] == DEFAULT_DEV_USER_ID

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
    assert planning_run.calculated_by_user_id == DEFAULT_DEV_USER_ID

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


def test_current_user_endpoint_exposes_pilot_role(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": DEFAULT_DEV_USER_ID,
        "username": "dev.planner",
        "display_name": "Development Planner",
        "role": "PLANNER",
        "active": True,
    }


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


def test_planning_run_calculation_actor_is_fk_constrained(client: TestClient) -> None:
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

    session_factory = create_session_factory()
    with session_factory() as session:
        planning_run = session.get(PlanningRun, planning_run_response.json()["id"])
        assert planning_run is not None
        planning_run.calculated_by_user_id = "missing-user"

        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            session.commit()


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


@pytest.mark.parametrize(
    (
        "role",
        "expected_view_status",
        "expected_export_status",
        "expected_upload_status",
        "expected_calculate_status",
        "expected_override_status",
    ),
    [
        ("PLANNER", 200, 201, 201, 200, 201),
        ("HOD", 200, 201, 403, 403, 403),
        ("MANAGEMENT", 200, 201, 403, 403, 403),
        ("ADMIN", 200, 403, 403, 403, 403),
    ],
)
def test_first_release_role_matrix_matches_recorded_decision(
    client: TestClient,
    role: str,
    expected_view_status: int,
    expected_export_status: int,
    expected_upload_status: int,
    expected_calculate_status: int,
    expected_override_status: int,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)
    recommendation_id = _first_recommendation_id(planning_run_id)
    before_counts = _audit_counts(planning_run_id)
    before_planning_run = _planning_run_audit(planning_run_id)
    before_recommendation_status = _recommendation_status(recommendation_id)
    _set_default_user(role=role, active=1)

    view_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/dashboard")
    export_response = client.post(
        f"/api/v1/planning-runs/{planning_run_id}/exports",
        json={"report_type": "MACHINE_LOAD", "file_format": "XLSX"},
    )
    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("role-matrix.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    override_response = client.post(
        "/api/v1/planner-overrides",
        json={
            "planning_run_id": planning_run_id,
            "entity_type": "RECOMMENDATION",
            "entity_id": recommendation_id,
            "override_decision": "ACCEPT",
            "reason": f"Role matrix check for {role}",
        },
    )
    calculate_response = client.post(f"/api/v1/planning-runs/{planning_run_id}/calculate")

    assert view_response.status_code == expected_view_status
    assert export_response.status_code == expected_export_status
    assert upload_response.status_code == expected_upload_status
    assert calculate_response.status_code == expected_calculate_status
    assert override_response.status_code == expected_override_status

    after_counts = _audit_counts(planning_run_id)
    after_planning_run = _planning_run_audit(planning_run_id)

    assert after_counts["uploads"] == before_counts["uploads"] + (1 if expected_upload_status == 201 else 0)
    assert after_counts["exports"] == before_counts["exports"] + (1 if expected_export_status == 201 else 0)
    assert after_counts["overrides"] == before_counts["overrides"] + (1 if expected_override_status == 201 else 0)
    assert after_counts["planning_runs"] == before_counts["planning_runs"]
    if expected_calculate_status == 403:
        assert after_planning_run == before_planning_run
    if expected_override_status == 403:
        after_recommendation_status = _recommendation_status(recommendation_id)
        assert after_recommendation_status == before_recommendation_status
    for denied_response, expected_status in (
        (export_response, expected_export_status),
        (upload_response, expected_upload_status),
        (calculate_response, expected_calculate_status),
        (override_response, expected_override_status),
    ):
        if expected_status == 403:
            assert denied_response.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"


def test_direct_services_enforce_first_release_role_boundaries_without_audit_side_effects(
    client: TestClient,
) -> None:
    planning_run_id = _create_calculated_planning_run(client)
    recommendation_id = _first_recommendation_id(planning_run_id)

    _set_default_user(role="HOD", active=1)
    before_counts = _audit_counts(planning_run_id)
    before_recommendation_status = _recommendation_status(recommendation_id)
    session_factory = create_session_factory()
    with session_factory() as session:
        planning_run = session.get(PlanningRun, planning_run_id)
        assert planning_run is not None

        with pytest.raises(HTTPException) as upload_exc:
            create_upload(
                file=_FakeUploadFile("direct.xlsx", workbook_bytes()),
                db=session,
                settings=get_settings(),
                uploaded_by_user_id=DEFAULT_DEV_USER_ID,
            )
        assert upload_exc.value.status_code == 403
        assert upload_exc.value.detail["code"] == "ROLE_NOT_ALLOWED"

        with pytest.raises(HTTPException) as planning_exc:
            create_planning_run(
                request=PlanningRunCreateRequest(
                    upload_batch_id=planning_run.upload_batch_id,
                    planning_start_date=None,
                    planning_horizon_days=7,
                ),
                db=session,
                created_by_user_id=DEFAULT_DEV_USER_ID,
            )
        assert planning_exc.value.status_code == 403
        assert planning_exc.value.detail["code"] == "ROLE_NOT_ALLOWED"

        with pytest.raises(HTTPException) as override_exc:
            create_planner_override(
                request=PlannerOverrideCreateRequest(
                    planning_run_id=planning_run_id,
                    entity_type="RECOMMENDATION",
                    entity_id=recommendation_id,
                    override_decision="ACCEPT",
                    reason="Direct service role denial should not mutate recommendation state.",
                ),
                db=session,
                user_id=DEFAULT_DEV_USER_ID,
            )
        assert override_exc.value.status_code == 403
        assert override_exc.value.detail["code"] == "ROLE_NOT_ALLOWED"

    assert _audit_counts(planning_run_id) == before_counts
    assert _recommendation_status(recommendation_id) == before_recommendation_status

    _set_default_user(role="ADMIN", active=1)
    before_counts = _audit_counts(planning_run_id)
    with session_factory() as session:
        with pytest.raises(HTTPException) as export_exc:
            generate_first_build_report_export(
                planning_run_id=planning_run_id,
                report_type="MACHINE_LOAD",
                file_format="XLSX",
                db=session,
                generated_by_user_id=DEFAULT_DEV_USER_ID,
            )
    assert export_exc.value.status_code == 403
    assert export_exc.value.detail["code"] == "ROLE_NOT_ALLOWED"
    assert _audit_counts(planning_run_id) == before_counts

    with session_factory() as session:
        with pytest.raises(HTTPException) as invalid_export_exc:
            generate_first_build_report_export(
                planning_run_id="missing-planning-run",
                report_type="UNKNOWN_REPORT",
                file_format="PDF",
                db=session,
                generated_by_user_id=DEFAULT_DEV_USER_ID,
            )
    assert invalid_export_exc.value.status_code == 403
    assert invalid_export_exc.value.detail["code"] == "ROLE_NOT_ALLOWED"


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


def test_inactive_default_user_cannot_read_or_download_planning_outputs(client: TestClient) -> None:
    planning_run_id = _create_calculated_planning_run(client)
    export_response = client.post(
        f"/api/v1/planning-runs/{planning_run_id}/exports",
        json={"report_type": "MACHINE_LOAD", "file_format": "XLSX"},
    )
    assert export_response.status_code == 201

    _set_default_user(role="PLANNER", active=0)

    dashboard_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/dashboard")
    planning_run_response = client.get(f"/api/v1/planning-runs/{planning_run_id}")
    export_list_response = client.get(f"/api/v1/planning-runs/{planning_run_id}/exports")
    export_download_response = client.get(export_response.json()["download_url"])

    for response in (dashboard_response, planning_run_response, export_list_response, export_download_response):
        assert response.status_code == 403
        assert response.json()["detail"] == {
            "code": "ACTING_USER_INACTIVE",
            "message": "Acting user is inactive and cannot perform this action.",
        }


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


def _audit_counts(planning_run_id: str) -> dict[str, int]:
    session_factory = create_session_factory()
    with session_factory() as session:
        return {
            "uploads": session.scalar(select(func.count()).select_from(UploadBatch)) or 0,
            "planning_runs": session.scalar(select(func.count()).select_from(PlanningRun)) or 0,
            "overrides": session.scalar(
                select(func.count()).select_from(PlannerOverride).where(PlannerOverride.planning_run_id == planning_run_id)
            )
            or 0,
            "exports": session.scalar(
                select(func.count()).select_from(ReportExport).where(ReportExport.planning_run_id == planning_run_id)
            )
            or 0,
        }


def _planning_run_audit(planning_run_id: str) -> tuple[str, str | None, str | None]:
    session_factory = create_session_factory()
    with session_factory() as session:
        planning_run = session.get(PlanningRun, planning_run_id)
        assert planning_run is not None
        return (planning_run.status, planning_run.calculated_at, planning_run.calculated_by_user_id)


def _recommendation_status(recommendation_id: str) -> str:
    session_factory = create_session_factory()
    with session_factory() as session:
        recommendation = session.get(Recommendation, recommendation_id)
        assert recommendation is not None
        return recommendation.status


def _set_default_user(*, role: str, active: int) -> None:
    session_factory = create_session_factory()
    with session_factory() as session:
        user = session.get(User, DEFAULT_DEV_USER_ID)
        assert user is not None
        user.role = role
        user.active = active
        session.commit()


class _FakeUploadFile:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        self.file = BytesIO(content)
