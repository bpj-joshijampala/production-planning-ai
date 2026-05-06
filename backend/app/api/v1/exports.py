import mimetypes
import json

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.report_export import ReportExportResponse
from app.services.report_exports import get_report_export, resolve_report_export_download

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{report_export_id}", response_model=ReportExportResponse)
def get_report_export_endpoint(
    report_export_id: str,
    db: Session = Depends(get_db),
) -> ReportExportResponse:
    return _to_response(get_report_export(report_export_id, db))


@router.get("/{report_export_id}/download")
def download_report_export_endpoint(
    report_export_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    report_export, file_path = resolve_report_export_download(report_export_id, db)
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=media_type,
        headers={"X-Report-Export-ID": report_export.id},
    )


def _to_response(report_export) -> ReportExportResponse:  # type: ignore[no-untyped-def]
    metadata = json.loads(report_export.metadata_json) if report_export.metadata_json else None
    return ReportExportResponse(
        id=report_export.id,
        planning_run_id=report_export.planning_run_id,
        report_type=report_export.report_type,
        file_path=report_export.file_path,
        file_format=report_export.file_format,
        generated_by_user_id=report_export.generated_by_user_id,
        generated_at=report_export.generated_at,
        metadata=metadata,
        download_url=f"/api/v1/exports/{report_export.id}/download",
    )
