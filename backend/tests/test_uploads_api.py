from collections.abc import Generator
from io import BytesIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.config import get_settings
from app.main import create_app
from app.models.upload import ImportStagingRow, RawUploadArtifact, UploadBatch
from app.services.uploads import create_upload
from tests.workbook_fixtures import REQUIRED_SHEETS, minimal_workbook_rows, workbook_bytes


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
    assert payload["status"] == "VALIDATED"
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


def test_upload_validation_flags_missing_required_sheet_and_column(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    del sheets["Vendor_Master"]
    sheets["Valve_Plan"][0].remove("Customer")
    sheets["Valve_Plan"][1].remove("Acme")

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("missing-structure.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert upload_response.status_code == 201
    upload_payload = upload_response.json()
    assert upload_payload["status"] == "VALIDATION_FAILED"
    assert upload_payload["validation_error_count"] >= 2

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issue_codes = {issue["issue_code"] for issue in issues_response.json()["issues"]}

    assert "MISSING_SHEET" in issue_codes
    assert "MISSING_COLUMN" in issue_codes


def test_upload_validation_flags_invalid_dates_numbers_and_booleans(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Valve_Plan"][1][3] = "not-a-date"
    sheets["Valve_Plan"][1][5] = "not-a-number"
    sheets["Component_Status"][1][3] = "maybe"

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("bad-values.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issues = issues_response.json()["issues"]
    issue_codes = {issue["issue_code"] for issue in issues}

    assert "INVALID_DATE" in issue_codes
    assert "INVALID_NUMBER" in issue_codes
    assert "INVALID_BOOLEAN" in issue_codes
    assert all(issue["row_number"] == 2 for issue in issues)


def test_upload_validation_warns_when_ready_component_missing_expected_ready_date(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Component_Status"][1][3] = "N"
    sheets["Component_Status"][1][5] = ""

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("ready-missing-date.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATED"
    assert upload_payload["validation_error_count"] == 0
    assert upload_payload["validation_warning_count"] == 1

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issues = issues_response.json()["issues"]

    assert issues[0]["severity"] == "WARNING"
    assert issues[0]["issue_code"] == "MISSING_EXPECTED_READY_DATE"


def test_upload_validation_blocks_when_not_ready_component_missing_expected_ready_date(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Component_Status"][1][5] = ""

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("not-ready-missing-date.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issue_codes = {issue["issue_code"] for issue in issues_response.json()["issues"]}

    assert "MISSING_EXPECTED_READY_DATE" in issue_codes


def test_upload_validation_flags_broken_master_references(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Component_Status"][1][0] = "V-404"
    sheets["Component_Status"][1][1] = "Unknown Component"
    sheets["Routing_Master"][0].append("Alt_Machine")
    sheets["Routing_Master"][1].append("DRILL")
    sheets["Routing_Master"][1][3] = "VTL"

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("broken-references.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issue_codes = {issue["issue_code"] for issue in issues_response.json()["issues"]}

    assert "UNKNOWN_VALVE_ID" in issue_codes
    assert "MISSING_ROUTING" in issue_codes
    assert "UNKNOWN_MACHINE_TYPE" in issue_codes
    assert "UNKNOWN_ALT_MACHINE" in issue_codes


def test_upload_validation_treats_missing_routing_as_warning_only(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Routing_Master"] = [sheets["Routing_Master"][0]]

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("missing-routing.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATED"
    assert upload_payload["validation_error_count"] == 0
    assert upload_payload["validation_warning_count"] == 1

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    routing_issues = [
        issue for issue in issues_response.json()["issues"] if issue["issue_code"] == "MISSING_ROUTING"
    ]

    assert len(routing_issues) == 1
    assert routing_issues[0]["severity"] == "WARNING"


def test_upload_validation_allows_missing_std_total_hours_when_setup_and_run_are_present(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Routing_Master"][0] = [
        "Component",
        "Operation No",
        "Operation Name",
        "Machine Type",
        "Std Setup Hrs",
        "Std Run Hrs",
        "Subcontract Allowed",
    ]
    sheets["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", 2, 6, "Y"]

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("routing-fallback.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATED"
    assert upload_payload["validation_error_count"] == 0


def test_upload_validation_blocks_routing_row_with_no_valid_standard_hours(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Routing_Master"][0] = [
        "Component",
        "Operation No",
        "Operation Name",
        "Machine Type",
        "Std Setup Hrs",
        "Std Run Hrs",
        "Std Total Hrs",
        "Subcontract Allowed",
    ]
    sheets["Routing_Master"][1] = ["Body", 10, "HBM roughing", "HBM", "", "", "", "Y"]

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("invalid-routing-hours.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issue_codes = {issue["issue_code"] for issue in issues_response.json()["issues"]}

    assert "INVALID_ROUTING_HOURS" in issue_codes


def test_upload_validation_flags_valve_without_component_status_rows(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Valve_Plan"].append(["V-200", "O-200", "Beta", "2026-05-02", "2026-04-29", 0.9])

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("missing-components.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    missing_component_issues = [
        issue for issue in issues_response.json()["issues"] if issue["issue_code"] == "MISSING_COMPONENT_STATUS"
    ]

    assert missing_component_issues
    assert missing_component_issues[0]["sheet_name"] == "Valve_Plan"


def test_upload_validation_generates_missing_component_line_numbers(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Component_Status"].append(["V-100", "Body", 1, "Y", "N", "2026-04-25", "Y"])

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("generated-lines.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_id = upload_response.json()["id"]

    from app.db.session import create_session_factory

    session_factory = create_session_factory()
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ImportStagingRow)
                .where(ImportStagingRow.upload_batch_id == upload_id)
                .where(ImportStagingRow.sheet_name == "Component_Status")
                .order_by(ImportStagingRow.row_number)
            )
        )

    payloads = [row.normalized_payload_json for row in rows]

    assert '"component_line_no":1' in payloads[0]
    assert '"component_line_no":2' in payloads[1]
    assert upload_response.json()["status"] == "VALIDATED"


def test_upload_validation_rejects_duplicate_component_line_numbers(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Component_Status"][0].insert(1, "Component_Line_No")
    sheets["Component_Status"][1].insert(1, 1)
    sheets["Component_Status"].append(["V-100", 1, "Body", 1, "Y", "N", "2026-04-25", "Y"])

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("duplicate-lines.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issue_codes = {issue["issue_code"] for issue in issues_response.json()["issues"]}

    assert "DUPLICATE_COMPONENT_LINE_NO" in issue_codes


def test_upload_validation_rejects_duplicate_canonical_business_keys(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Valve_Plan"].append(["V-100", "O-101", "Acme 2", "2026-05-02", "2026-04-29", 2.0])
    sheets["Routing_Master"].append(["Body", 10, "HBM finish", "HBM", 2, "N"])
    sheets["Machine_Master"].append(["HBM-1", "HBM", 8, 75, 4, "Y"])
    sheets["Vendor_Master"].append(["VEN-1", "Vendor One Duplicate", "HBM", 4, 1, "Y"])

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("duplicate-keys.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issue_codes = {issue["issue_code"] for issue in issues_response.json()["issues"]}

    assert "DUPLICATE_VALVE_ID" in issue_codes
    assert "DUPLICATE_ROUTING_OPERATION" in issue_codes
    assert "DUPLICATE_MACHINE_ID" in issue_codes
    assert "DUPLICATE_VENDOR_ID" in issue_codes


def test_upload_validation_rejects_duplicate_normalized_columns(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Valve_Plan"][0].insert(1, "Valve_ID")
    sheets["Valve_Plan"][1].insert(1, "V-999")

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("duplicate-columns.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    duplicate_column_issues = [
        issue for issue in issues_response.json()["issues"] if issue["issue_code"] == "DUPLICATE_COLUMN"
    ]

    assert duplicate_column_issues
    assert duplicate_column_issues[0]["sheet_name"] == "Valve_Plan"
    assert duplicate_column_issues[0]["field_name"] == "valve_id"


def test_upload_validation_rejects_required_sheets_with_no_data_rows(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets = {sheet_name: [rows[0]] for sheet_name, rows in sheets.items()}

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("headers-only.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATION_FAILED"

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issues = issues_response.json()["issues"]

    assert {issue["sheet_name"] for issue in issues if issue["issue_code"] == "EMPTY_SHEET"} == (
        set(REQUIRED_SHEETS) - {"Routing_Master"}
    )


def test_upload_validation_keeps_vendor_gap_as_warning(client: TestClient) -> None:
    sheets = minimal_workbook_rows()
    sheets["Vendor_Master"][1][5] = "N"

    upload_response = client.post(
        "/api/v1/uploads",
        files={"file": ("vendor-warning.xlsx", workbook_bytes(sheets=sheets), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    upload_payload = upload_response.json()

    assert upload_payload["status"] == "VALIDATED"
    assert upload_payload["validation_error_count"] == 0
    assert upload_payload["validation_warning_count"] == 1

    issues_response = client.get(f"/api/v1/uploads/{upload_payload['id']}/validation-issues")
    issues = issues_response.json()["issues"]

    assert issues[0]["severity"] == "WARNING"
    assert issues[0]["issue_code"] == "NO_APPROVED_VENDOR"


def test_create_upload_removes_stored_file_when_database_commit_fails(tmp_path) -> None:  # type: ignore[no-untyped-def]
    upload_dir = tmp_path / "uploads"
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'unused.sqlite3').as_posix()}",
        upload_dir=upload_dir,
        export_dir=tmp_path / "exports",
    )
    failing_db = _FailingCommitSession()
    upload_file = _FakeUploadFile(
        filename="plan.xlsx",
        content=workbook_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    with pytest.raises(RuntimeError, match="database commit failed"):
        create_upload(file=upload_file, db=failing_db, settings=settings)  # type: ignore[arg-type]

    assert failing_db.rolled_back is True
    assert not list(upload_dir.rglob("*"))


class _FailingCommitSession:
    def __init__(self) -> None:
        self.rolled_back = False

    def add(self, _row: object) -> None:
        return None

    def flush(self) -> None:
        return None

    def add_all(self, _rows: list[object]) -> None:
        return None

    def commit(self) -> None:
        raise RuntimeError("database commit failed")

    def rollback(self) -> None:
        self.rolled_back = True


class _FakeUploadFile:
    def __init__(self, *, filename: str, content: bytes, content_type: str) -> None:
        self.filename = filename
        self.file = BytesIO(content)
        self.content_type = content_type
