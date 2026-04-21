from pydantic import BaseModel


class RawUploadArtifactResponse(BaseModel):
    id: str
    upload_batch_id: str
    storage_path: str
    mime_type: str | None
    created_at: str

    model_config = {"from_attributes": True}


class UploadBatchResponse(BaseModel):
    id: str
    original_filename: str
    stored_filename: str
    file_hash: str
    file_size_bytes: int
    uploaded_by_user_id: str
    uploaded_at: str
    status: str
    validation_error_count: int
    validation_warning_count: int
    artifact: RawUploadArtifactResponse


class ValidationIssueResponse(BaseModel):
    id: str
    upload_batch_id: str
    staging_row_id: str | None
    sheet_name: str | None
    row_number: int | None
    severity: str
    issue_code: str
    message: str
    field_name: str | None
    created_at: str

    model_config = {"from_attributes": True}


class ValidationIssueSummary(BaseModel):
    blocking: int
    warning: int
    total: int


class ValidationIssuesResponse(BaseModel):
    upload_batch_id: str
    summary: ValidationIssueSummary
    issues: list[ValidationIssueResponse]
