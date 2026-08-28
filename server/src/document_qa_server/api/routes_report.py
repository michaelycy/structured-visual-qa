"""报告导出路由：从对比记录导出 XLSX/HTML 验收交付物。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from document_qa_server.services import (
    ReportExportService,
    ReportNotFoundError,
    ReportUnavailableError,
)

router = APIRouter(prefix="/api/report", tags=["report"])

class ExportRequest(BaseModel):
    """导出请求：历史记录 ID + 目标格式。"""

    record_id: str = Field(min_length=1)
    format: Literal["xlsx", "html"]


@router.post("/export")
def export_report(request: ExportRequest, http: Request) -> FileResponse:
    """按历史记录导出 XLSX 或 HTML，返回文件流。"""

    service: ReportExportService = http.app.state.report_exports
    try:
        result = service.export(request.record_id, request.format)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReportUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        result.path, media_type=result.media_type, filename=result.path.name
    )
