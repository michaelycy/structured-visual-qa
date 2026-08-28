"""报告导出用例：读取历史报告并生成验收文件。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from document_qa.reporting.html_reporter import export_html
from document_qa.reporting.xlsx_reporter import export_xlsx
from document_qa.schemas import QAReport

from document_qa_server.services.history_service import CompareHistoryService


class ReportNotFoundError(ValueError):
    """指定历史记录不存在。"""


class ReportUnavailableError(ValueError):
    """历史记录存在但没有可导出的完整报告。"""


@dataclass(frozen=True)
class ReportExportResult:
    """报告导出结果：安全文件路径和 HTTP 媒体类型。"""

    path: Path
    media_type: str


class ReportExportService:
    """协调历史读取、Schema 校验和 XLSX/HTML 导出。"""

    def __init__(
        self,
        *,
        artifacts_dir: Path,
        history: CompareHistoryService,
    ) -> None:
        """注入产物根目录与历史服务。"""

        self._exports_dir = artifacts_dir / "exports"
        self._history = history

    def export(
        self,
        record_id: str,
        output_format: Literal["xlsx", "html"],
    ) -> ReportExportResult:
        """校验历史报告并导出指定格式。"""

        try:
            record = self._history.get(record_id)
        except ValueError as exc:
            raise ReportNotFoundError(str(exc)) from exc
        if not record.report:
            raise ReportUnavailableError("该记录不含完整报告")

        report = QAReport.model_validate(record.report)
        self._exports_dir.mkdir(parents=True, exist_ok=True)
        if output_format == "xlsx":
            path = export_xlsx(report, self._exports_dir / f"{record_id}.xlsx")
            media_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            path = export_html(report, self._exports_dir / f"{record_id}.html")
            media_type = "text/html"
        return ReportExportResult(path=path, media_type=media_type)
