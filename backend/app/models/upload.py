from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_uuid
from app.core.time import utc_now_iso
from app.db.base import Base


class UploadBatch(Base):
    __tablename__ = "upload_batches"
    __table_args__ = (
        CheckConstraint(
            "status in ('UPLOADED', 'VALIDATION_FAILED', 'VALIDATED', 'PROMOTED', 'CALCULATED')",
            name="ck_upload_batches_status",
        ),
        CheckConstraint("file_size_bytes > 0", name="ck_upload_batches_file_size_positive"),
        CheckConstraint("validation_error_count >= 0", name="ck_upload_batches_error_count_nonnegative"),
        CheckConstraint("validation_warning_count >= 0", name="ck_upload_batches_warning_count_nonnegative"),
        Index("ix_upload_batches_uploaded_at", "uploaded_at"),
        Index("ix_upload_batches_uploaded_by_user_id", "uploaded_by_user_id"),
        Index("ix_upload_batches_status", "status"),
        Index("ix_upload_batches_file_hash", "file_hash"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    uploaded_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
    status: Mapped[str] = mapped_column(String, nullable=False, default="UPLOADED")
    validation_error_count: Mapped[int] = mapped_column(nullable=False, default=0)
    validation_warning_count: Mapped[int] = mapped_column(nullable=False, default=0)


class RawUploadArtifact(Base):
    __tablename__ = "raw_upload_artifacts"
    __table_args__ = (UniqueConstraint("upload_batch_id", name="uq_raw_upload_artifacts_upload_batch_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    upload_batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class ImportStagingRow(Base):
    __tablename__ = "import_staging_rows"
    __table_args__ = (
        CheckConstraint("json_valid(normalized_payload_json)", name="ck_import_staging_rows_payload_json"),
        Index("ix_import_staging_rows_upload_sheet", "upload_batch_id", "sheet_name"),
        Index("ix_import_staging_rows_upload_sheet_row", "upload_batch_id", "sheet_name", "row_number"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    upload_batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String, nullable=False)
    row_number: Mapped[int] = mapped_column(nullable=False)
    normalized_payload_json: Mapped[str] = mapped_column(String, nullable=False)
    row_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)


class ImportValidationIssue(Base):
    __tablename__ = "import_validation_issues"
    __table_args__ = (
        CheckConstraint("severity in ('BLOCKING', 'WARNING')", name="ck_import_validation_issues_severity"),
        Index("ix_import_validation_issues_upload_severity", "upload_batch_id", "severity"),
        Index("ix_import_validation_issues_upload_sheet_row", "upload_batch_id", "sheet_name", "row_number"),
        Index("ix_import_validation_issues_issue_code", "issue_code"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    upload_batch_id: Mapped[str] = mapped_column(ForeignKey("upload_batches.id"), nullable=False)
    staging_row_id: Mapped[str | None] = mapped_column(ForeignKey("import_staging_rows.id"), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String, nullable=True)
    row_number: Mapped[int | None] = mapped_column(nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    issue_code: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utc_now_iso)
