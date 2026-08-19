"""报告导出路由：从对比记录导出 XLSX/HTML 验收交付物。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from document_qa.reporting.html_reporter import export_html
from document_qa.reporting.xlsx_reporter import export_xlsx
from document_qa.schemas import QAReport
from document_qa_server.services import CompareHistoryService

router = APIRouter(prefix="/api/report", tags=["report"])

# 交付物下载根目录；文件名由服务端生成，前端只管接收。
EXPORT_DIR_NAME = "exports"


class ExportRequest(BaseModel):
    """导出请求：历史记录 ID + 目标格式。"""

    record_id: str = Field(min_length=1)
    format: Literal["xlsx", "html"]


@router.post("/export")
def export_report(request: ExportRequest, http: Request) -> FileResponse:
    """按历史记录导出 XLSX 或 HTML，返回文件流。"""

    history: CompareHistoryService = http.app.state.history
    try:
        record = history.get(request.record_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not record.report:
        raise HTTPException(status_code=409, detail="该记录不含完整报告")

    report = QAReport.model_validate(record.report)
    # artifacts_dir 在应用级状态上（http.app.state），不是请求级。
    exports_dir = Path(http.app.state.artifacts_dir) / EXPORT_DIR_NAME
    exports_dir.mkdir(parents=True, exist_ok=True)
    if request.format == "xlsx":
        path = export_xlsx(report, exports_dir / f"{request.record_id}.xlsx")
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        path = export_html(report, exports_dir / f"{request.record_id}.html")
        media_type = "text/html"
    return FileResponse(
        path, media_type=media_type, filename=path.name
    )
