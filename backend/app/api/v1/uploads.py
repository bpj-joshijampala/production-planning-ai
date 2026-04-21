from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.upload import UploadBatchResponse, ValidationIssuesResponse
from app.services.uploads import create_upload, get_upload, get_validation_issues

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=UploadBatchResponse, status_code=status.HTTP_201_CREATED)
def upload_workbook(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadBatchResponse:
    return create_upload(file=file, db=db, settings=settings)


@router.get("/{upload_batch_id}", response_model=UploadBatchResponse)
def read_upload(upload_batch_id: str, db: Session = Depends(get_db)) -> UploadBatchResponse:
    return get_upload(upload_batch_id=upload_batch_id, db=db)


@router.get("/{upload_batch_id}/validation-issues", response_model=ValidationIssuesResponse)
def read_validation_issues(upload_batch_id: str, db: Session = Depends(get_db)) -> ValidationIssuesResponse:
    return get_validation_issues(upload_batch_id=upload_batch_id, db=db)
