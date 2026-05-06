import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import EXPORT_ROLES, WRITE_ROLES, require_current_user_roles
from app.db.session import get_db
from app.models.output import ReportExport
from app.models.user import User
from app.schemas.report_export import ReportExportCreateRequest, ReportExportListResponse, ReportExportResponse
from app.schemas.dashboard import (
    AssemblyRiskListResponse,
    ComponentStatusListResponse,
    FlowBlockerListResponse,
    IncomingLoadListResponse,
    MachineLoadListResponse,
    PlanningRunDashboardSummaryResponse,
    QueueOperationListResponse,
    RecommendationListResponse,
    ThroughputSummaryResponse,
    ValveReadinessListResponse,
    VendorLoadListResponse,
)
from app.schemas.planning_run import PlanningRunCreateRequest, PlanningRunListResponse, PlanningRunResponse
from app.services.dashboard_queries import (
    get_dashboard_summary,
    get_throughput_summary,
    list_assembly_risk,
    list_component_status,
    list_flow_blockers,
    list_incoming_load,
    list_machine_load,
    list_machine_queue,
    list_recommendations,
    list_valve_readiness,
    list_vendor_load,
)
from app.services.planning_runs import (
    calculate_planning_run_response,
    create_planning_run,
    get_planning_run,
    list_planning_runs,
)
from app.services.report_exports import generate_first_build_report_export, list_report_exports

router = APIRouter(prefix="/planning-runs", tags=["planning-runs"])
logger = logging.getLogger(__name__)


@router.post("", response_model=PlanningRunResponse, status_code=status.HTTP_201_CREATED)
def create_planning_run_endpoint(
    request: PlanningRunCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user_roles(*WRITE_ROLES)),
) -> PlanningRunResponse:
    return create_planning_run(request=request, db=db, created_by_user_id=current_user.id)


@router.post("/{planning_run_id}/calculate", response_model=PlanningRunResponse)
def calculate_planning_run_endpoint(
    planning_run_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_current_user_roles(*WRITE_ROLES)),
) -> PlanningRunResponse:
    try:
        return calculate_planning_run_response(planning_run_id=planning_run_id, db=db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Planning calculation failed planning_run_id=%s", planning_run_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "CALCULATION_FAILED",
                "message": "Planning calculation failed. Review the PlanningRun error message, fix the input data or settings, and retry.",
            },
        ) from exc


@router.post("/{planning_run_id}/exports", response_model=ReportExportResponse, status_code=status.HTTP_201_CREATED)
def create_report_export_endpoint(
    planning_run_id: str,
    request: ReportExportCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user_roles(*EXPORT_ROLES)),
) -> ReportExportResponse:
    try:
        report_export = generate_first_build_report_export(
            planning_run_id=planning_run_id,
            report_type=request.report_type,
            file_format=request.file_format,
            generated_by_user_id=current_user.id,
            db=db,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Report export failed planning_run_id=%s report_type=%s file_format=%s",
            planning_run_id,
            request.report_type,
            request.file_format,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "EXPORT_FAILED",
                "message": "Report export failed. Retry the export or contact support if the generated file is still unavailable.",
            },
        ) from exc
    return _report_export_response(report_export, db)


@router.get("/{planning_run_id}/exports", response_model=ReportExportListResponse)
def list_report_exports_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    latest_only: bool = Query(False),
    db: Session = Depends(get_db),
) -> ReportExportListResponse:
    report_exports, total = list_report_exports(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        latest_only=latest_only,
    )
    return ReportExportListResponse(
        items=[_report_export_response(report_export, db) for report_export in report_exports],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=PlanningRunListResponse)
def list_planning_runs_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    latest_only: bool = Query(False),
    db: Session = Depends(get_db),
) -> PlanningRunListResponse:
    return list_planning_runs(
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        latest_only=latest_only,
    )


@router.get("/{planning_run_id}", response_model=PlanningRunResponse)
def get_planning_run_endpoint(
    planning_run_id: str,
    db: Session = Depends(get_db),
) -> PlanningRunResponse:
    return get_planning_run(planning_run_id=planning_run_id, db=db)


@router.get("/{planning_run_id}/dashboard", response_model=PlanningRunDashboardSummaryResponse)
def get_dashboard_endpoint(
    planning_run_id: str,
    db: Session = Depends(get_db),
) -> PlanningRunDashboardSummaryResponse:
    return get_dashboard_summary(planning_run_id=planning_run_id, db=db)


@router.get("/{planning_run_id}/incoming-load", response_model=IncomingLoadListResponse)
def list_incoming_load_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
    direction: Literal["asc", "desc"] = Query("asc"),
    customer: str | None = Query(None),
    db: Session = Depends(get_db),
) -> IncomingLoadListResponse:
    return list_incoming_load(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        customer=customer,
    )


@router.get("/{planning_run_id}/valve-readiness", response_model=ValveReadinessListResponse)
def list_valve_readiness_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
    direction: Literal["asc", "desc"] = Query("asc"),
    customer: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> ValveReadinessListResponse:
    return list_valve_readiness(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        customer=customer,
        status_filter=status_filter,
    )


@router.get("/{planning_run_id}/component-status", response_model=ComponentStatusListResponse)
def list_component_status_endpoint(
    planning_run_id: str,
    valve_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ComponentStatusListResponse:
    return list_component_status(
        planning_run_id=planning_run_id,
        valve_id=valve_id,
        db=db,
        page=page,
        page_size=page_size,
    )


@router.get("/{planning_run_id}/machine-load", response_model=MachineLoadListResponse)
def list_machine_load_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
    direction: Literal["asc", "desc"] = Query("asc"),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> MachineLoadListResponse:
    return list_machine_load(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        status_filter=status_filter,
    )


@router.get("/{planning_run_id}/machine-load/{machine_type}/queue", response_model=QueueOperationListResponse)
def list_machine_queue_endpoint(
    planning_run_id: str,
    machine_type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
    direction: Literal["asc", "desc"] = Query("asc"),
    customer: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> QueueOperationListResponse:
    return list_machine_queue(
        planning_run_id=planning_run_id,
        machine_type=machine_type,
        db=db,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        customer=customer,
        status_filter=status_filter,
    )


@router.get("/{planning_run_id}/subcontract-recommendations", response_model=RecommendationListResponse)
def list_recommendations_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
    direction: Literal["asc", "desc"] = Query("asc"),
    customer: str | None = Query(None),
    recommendation_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> RecommendationListResponse:
    return list_recommendations(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        customer=customer,
        recommendation_type=recommendation_type,
        status_filter=status_filter,
    )


@router.get("/{planning_run_id}/flow-blockers", response_model=FlowBlockerListResponse)
def list_flow_blockers_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
    direction: Literal["asc", "desc"] = Query("asc"),
    customer: str | None = Query(None),
    blocker_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> FlowBlockerListResponse:
    return list_flow_blockers(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        customer=customer,
        blocker_type=blocker_type,
        status_filter=status_filter,
    )


@router.get("/{planning_run_id}/vendor-load", response_model=VendorLoadListResponse)
def list_vendor_load_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str | None = Query(None),
    direction: Literal["asc", "desc"] = Query("asc"),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> VendorLoadListResponse:
    return list_vendor_load(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        sort=sort,
        direction=direction,
        status_filter=status_filter,
    )


@router.get("/{planning_run_id}/assembly-risk", response_model=AssemblyRiskListResponse)
def list_assembly_risk_endpoint(
    planning_run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    customer: str | None = Query(None),
    db: Session = Depends(get_db),
) -> AssemblyRiskListResponse:
    return list_assembly_risk(
        planning_run_id=planning_run_id,
        db=db,
        page=page,
        page_size=page_size,
        customer=customer,
    )


@router.get("/{planning_run_id}/throughput", response_model=ThroughputSummaryResponse)
def get_throughput_endpoint(
    planning_run_id: str,
    db: Session = Depends(get_db),
) -> ThroughputSummaryResponse:
    return get_throughput_summary(planning_run_id=planning_run_id, db=db)


def _report_export_response(report_export: ReportExport, db: Session) -> ReportExportResponse:
    generated_by_user = db.get(User, report_export.generated_by_user_id)
    return ReportExportResponse(
        id=report_export.id,
        planning_run_id=report_export.planning_run_id,
        report_type=report_export.report_type,
        file_path=report_export.file_path,
        file_format=report_export.file_format,
        generated_by_user_id=report_export.generated_by_user_id,
        generated_by_user_display_name=None if generated_by_user is None else generated_by_user.display_name,
        generated_at=report_export.generated_at,
        metadata=json.loads(report_export.metadata_json) if report_export.metadata_json else None,
        download_url=f"/api/v1/exports/{report_export.id}/download",
    )
