import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import VIEW_ROLES, WRITE_ROLES, require_current_user_roles
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.upload import UploadBatchResponse, ValidationIssuesResponse
from app.services.uploads import create_upload, get_upload, get_validation_issues

router = APIRouter(
    prefix="/uploads",
    tags=["uploads"],
    dependencies=[Depends(require_current_user_roles(*VIEW_ROLES))],
)
logger = logging.getLogger(__name__)


@router.post("", response_model=UploadBatchResponse, status_code=status.HTTP_201_CREATED)
def upload_workbook(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(require_current_user_roles(*WRITE_ROLES)),
) -> UploadBatchResponse:
    try:
        return create_upload(file=file, db=db, settings=settings, uploaded_by_user_id=current_user.id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload failed while saving and validating workbook filename=%s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "UPLOAD_FAILED",
                "message": "Upload could not be saved and validated. Retry the upload or contact support if the problem continues.",
            },
        ) from exc


@router.get("/{upload_batch_id}", response_model=UploadBatchResponse)
def read_upload(upload_batch_id: str, db: Session = Depends(get_db)) -> UploadBatchResponse:
    return get_upload(upload_batch_id=upload_batch_id, db=db)


@router.get("/{upload_batch_id}/validation-issues", response_model=ValidationIssuesResponse)
def read_validation_issues(upload_batch_id: str, db: Session = Depends(get_db)) -> ValidationIssuesResponse:
    return get_validation_issues(upload_batch_id=upload_batch_id, db=db)
