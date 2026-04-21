from hashlib import sha256
import json
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.imports.workbook import ParsedWorkbookRow, WorkbookParseError, parse_workbook
from app.models.upload import ImportStagingRow, ImportValidationIssue, RawUploadArtifact, UploadBatch
from app.schemas.upload import (
    RawUploadArtifactResponse,
    UploadBatchResponse,
    ValidationIssueResponse,
    ValidationIssuesResponse,
    ValidationIssueSummary,
)

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
SUPPORTED_EXTENSION = ".xlsx"
UNSUPPORTED_EXTENSIONS = {".xls", ".xlsm", ".csv", ".tsv"}


def create_upload(file: UploadFile, db: Session, settings: Settings) -> UploadBatchResponse:
    original_filename = _safe_filename(file.filename)
    _validate_supported_extension(original_filename)

    content = file.file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_UPLOAD", "message": "Uploaded file is empty."},
        )

    max_upload_size_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "UPLOAD_TOO_LARGE",
                "message": f"Uploaded file exceeds the {settings.max_upload_size_mb} MB limit.",
            },
        )

    try:
        parsed_rows = parse_workbook(content)
    except WorkbookParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_WORKBOOK", "message": str(exc)},
        ) from exc

    upload_id = new_uuid()
    artifact_id = new_uuid()
    uploaded_at = utc_now_iso()
    upload_dir = settings.upload_dir / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = original_filename
    storage_path = upload_dir / stored_filename
    storage_path.write_bytes(content)

    upload_batch = UploadBatch(
        id=upload_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_hash=sha256(content).hexdigest(),
        file_size_bytes=len(content),
        uploaded_by_user_id=DEV_USER_ID,
        uploaded_at=uploaded_at,
        status="UPLOADED",
        validation_error_count=0,
        validation_warning_count=0,
    )
    artifact = RawUploadArtifact(
        id=artifact_id,
        upload_batch_id=upload_id,
        storage_path=str(storage_path),
        mime_type=file.content_type,
        created_at=uploaded_at,
    )

    db.add(upload_batch)
    db.flush()
    db.add(artifact)
    db.add_all(_to_staging_rows(upload_id, parsed_rows, uploaded_at))
    db.commit()
    db.refresh(upload_batch)
    db.refresh(artifact)

    return _to_upload_response(upload_batch, artifact)


def get_upload(upload_batch_id: str, db: Session) -> UploadBatchResponse:
    upload_batch, artifact = _load_upload_with_artifact(upload_batch_id, db)
    return _to_upload_response(upload_batch, artifact)


def get_validation_issues(upload_batch_id: str, db: Session) -> ValidationIssuesResponse:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None:
        raise_upload_not_found(upload_batch_id)

    issues = list(
        db.scalars(
            select(ImportValidationIssue)
            .where(ImportValidationIssue.upload_batch_id == upload_batch_id)
            .order_by(
                ImportValidationIssue.severity,
                ImportValidationIssue.sheet_name,
                ImportValidationIssue.row_number,
                ImportValidationIssue.created_at,
            )
        )
    )
    blocking = sum(1 for issue in issues if issue.severity == "BLOCKING")
    warning = sum(1 for issue in issues if issue.severity == "WARNING")

    return ValidationIssuesResponse(
        upload_batch_id=upload_batch_id,
        summary=ValidationIssueSummary(blocking=blocking, warning=warning, total=len(issues)),
        issues=[ValidationIssueResponse.model_validate(issue) for issue in issues],
    )


def _load_upload_with_artifact(upload_batch_id: str, db: Session) -> tuple[UploadBatch, RawUploadArtifact]:
    upload_batch = db.get(UploadBatch, upload_batch_id)
    if upload_batch is None:
        raise_upload_not_found(upload_batch_id)

    artifact = db.scalar(select(RawUploadArtifact).where(RawUploadArtifact.upload_batch_id == upload_batch_id))
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "UPLOAD_ARTIFACT_MISSING",
                "message": f"Upload {upload_batch_id} does not have a raw file artifact.",
            },
        )

    return upload_batch, artifact


def _to_upload_response(upload_batch: UploadBatch, artifact: RawUploadArtifact) -> UploadBatchResponse:
    return UploadBatchResponse(
        id=upload_batch.id,
        original_filename=upload_batch.original_filename,
        stored_filename=upload_batch.stored_filename,
        file_hash=upload_batch.file_hash,
        file_size_bytes=upload_batch.file_size_bytes,
        uploaded_by_user_id=upload_batch.uploaded_by_user_id,
        uploaded_at=upload_batch.uploaded_at,
        status=upload_batch.status,
        validation_error_count=upload_batch.validation_error_count,
        validation_warning_count=upload_batch.validation_warning_count,
        artifact=RawUploadArtifactResponse.model_validate(artifact),
    )


def _to_staging_rows(
    upload_batch_id: str, parsed_rows: list[ParsedWorkbookRow], created_at: str
) -> list[ImportStagingRow]:
    return [
        ImportStagingRow(
            id=new_uuid(),
            upload_batch_id=upload_batch_id,
            sheet_name=row.sheet_name,
            row_number=row.row_number,
            normalized_payload_json=json.dumps(row.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
            row_hash=row.row_hash,
            created_at=created_at,
        )
        for row in parsed_rows
    ]


def _safe_filename(filename: str | None) -> str:
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_FILENAME", "message": "Uploaded file must include a filename."},
        )
    return safe_name


def _validate_supported_extension(filename: str) -> None:
    extension = Path(filename).suffix.lower()
    if extension != SUPPORTED_EXTENSION:
        known_message = "Unsupported upload format. Only .xlsx files are supported."
        if extension in UNSUPPORTED_EXTENSIONS:
            known_message = f"{extension} uploads are not supported. Please upload the standard .xlsx workbook."

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "UNSUPPORTED_FILE_TYPE", "message": known_message},
        )


def raise_upload_not_found(upload_batch_id: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "UPLOAD_NOT_FOUND", "message": f"Upload {upload_batch_id} was not found."},
    )
