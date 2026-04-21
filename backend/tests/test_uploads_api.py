from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import create_app
from app.models.upload import ImportStagingRow, RawUploadArtifact, UploadBatch
from tests.workbook_fixtures import REQUIRED_SHEETS, workbook_bytes


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "uploads_api.sqlite3"
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


def test_upload_xlsx_stores_artifact_and_metadata(client: TestClient) -> None:
    content = workbook_bytes()

    response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                "machine_plan.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["original_filename"] == "machine_plan.xlsx"
    assert payload["status"] == "UPLOADED"
    assert payload["file_size_bytes"] == len(content)
    assert payload["validation_error_count"] == 0
    assert payload["validation_warning_count"] == 0
    assert payload["artifact"]["storage_path"].endswith("machine_plan.xlsx")


def test_get_upload_returns_artifact_trace(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("trace.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_id = upload_response.json()["id"]

    response = client.get(f"/api/v1/uploads/{upload_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == upload_id
    assert payload["artifact"]["upload_batch_id"] == upload_id
    assert Path(payload["artifact"]["storage_path"]).exists()


@pytest.mark.parametrize("filename", ["legacy.xls", "macro.xlsm", "data.csv", "data.tsv", "notes.txt"])
def test_upload_rejects_unsupported_file_types(client: TestClient, filename: str) -> None:
    response = client.post("/api/v1/uploads", files={"file": (filename, b"not supported", "application/octet-stream")})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_validation_issues_endpoint_returns_empty_summary_for_artifact_only_upload(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("clean.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_id = upload_response.json()["id"]

    response = client.get(f"/api/v1/uploads/{upload_id}/validation-issues")

    assert response.status_code == 200
    assert response.json() == {
        "upload_batch_id": upload_id,
        "summary": {"blocking": 0, "warning": 0, "total": 0},
        "issues": [],
    }


def test_get_missing_upload_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/uploads/missing-upload")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "UPLOAD_NOT_FOUND"


def test_upload_records_are_queryable_in_database(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("queryable.xlsx", workbook_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_id = response.json()["id"]

    from app.db.session import create_session_factory

    session_factory = create_session_factory()
    with session_factory() as session:
        upload = session.scalar(select(UploadBatch).where(UploadBatch.id == upload_id))
        artifact = session.scalar(select(RawUploadArtifact).where(RawUploadArtifact.upload_batch_id == upload_id))

    assert upload is not None
    assert upload.original_filename == "queryable.xlsx"
    assert artifact is not None
    assert Path(artifact.storage_path).exists()


def test_upload_stages_rows_for_supported_workbook_sheets(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("staged.xlsx", workbook_bytes(include_extra_sheet=True), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_id = response.json()["id"]

    from app.db.session import create_session_factory

    session_factory = create_session_factory()
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ImportStagingRow)
                .where(ImportStagingRow.upload_batch_id == upload_id)
                .order_by(ImportStagingRow.sheet_name)
            )
        )

    assert {row.sheet_name for row in rows} == set(REQUIRED_SHEETS)
    assert len(rows) == 5
    assert all(row.row_hash for row in rows)


def test_upload_rejects_unreadable_xlsx(client: TestClient) -> None:
    response = client.post(
        "/api/v1/uploads",
        files={
            "file": (
                "broken.xlsx",
                b"not really an xlsx file",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_WORKBOOK"
