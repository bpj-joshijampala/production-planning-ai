from pydantic import BaseModel
from typing import Literal, Any


ReportType = Literal[
    "MACHINE_LOAD",
    "SUBCONTRACT_PLAN",
    "VALVE_READINESS",
    "FLOW_BLOCKER",
    "WEEKLY_PLANNING",
    "DAILY_EXECUTION",
    "A3_PLANNING",
]
ReportFileFormat = Literal["XLSX", "PDF", "HTML"]


class ReportExportCreateRequest(BaseModel):
    report_type: ReportType
    file_format: ReportFileFormat = "XLSX"


class ReportExportResponse(BaseModel):
    id: str
    planning_run_id: str
    report_type: str
    file_path: str
    file_format: str
    generated_by_user_id: str
    generated_at: str
    metadata: dict[str, Any] | None
    download_url: str
