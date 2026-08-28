"""洞察路由：复核闭环的误报归因统计与调优建议（只读，T21）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/insights", tags=["insights"])


class RepairReportDownloadRequest(BaseModel):
    """AI 修复报告下载范围；cluster_id 来自结构化报告接口。"""

    cluster_ids: list[str] = Field(min_length=1)


@router.get("/review")
def review_insight(http: Request) -> dict:
    """返回复核判定的误报归因统计：按 Issue 类型的结论分布与误报率。"""

    return http.app.state.insights.summary().model_dump(mode="json")


@router.get("/review/suggestions")
def review_tuning_suggestions(http: Request) -> dict:
    """返回基于复核样本的调优建议与 DRAFT 草案；只读计算，不落任何存储。"""

    return http.app.state.insights.tuning_advice().model_dump(mode="json")


@router.get("/review/repair-report")
def review_repair_report(http: Request) -> dict:
    """返回供代码修复 AI 使用的结构化误报诊断报告。"""

    return http.app.state.insights.repair_report().model_dump(mode="json")


@router.get("/review/repair-report/download")
def download_review_repair_report(http: Request) -> Response:
    """兼容下载全量 Markdown；规则页使用 POST 精确选择误报模式。"""

    content = http.app.state.insights.repair_report_markdown()
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-repair-report.md"'},
    )


@router.post("/review/repair-report/download")
def download_selected_review_repair_report(
    request: RepairReportDownloadRequest,
    http: Request,
) -> Response:
    """按所选误报聚类下载 Markdown，不写入服务端文件系统。"""

    try:
        content = http.app.state.insights.repair_report_markdown(set(request.cluster_ids))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ai-repair-report.md"'},
    )
