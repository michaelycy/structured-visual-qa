"""复核闭环路由：Issue 判定的保存与查询。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from document_qa_server.services import ReviewService

router = APIRouter(prefix="/api/review", tags=["review"])


class DecisionRequest(BaseModel):
    """一条 Issue 判定的提交内容。"""

    task_id: str = Field(min_length=1)
    report_summary: dict = Field(default_factory=dict)
    issue_id: str = Field(min_length=1)
    decision: Literal["confirmed", "false_positive", "ignored"]
    note: str = ""


def _service(http: Request) -> ReviewService:
    """从应用状态取复核服务实例。"""

    return http.app.state.reviews


@router.post("/decision")
def save_decision(request: DecisionRequest, http: Request) -> dict:
    """保存一条判定，返回该任务的最新复核记录。"""

    service = _service(http)
    try:
        record = service.save_decision(
            request.task_id,
            request.report_summary,
            request.issue_id,
            request.decision,
            request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@router.get("/task/{task_id}")
def get_task(task_id: str, http: Request) -> dict:
    """查询任务的复核记录；未初始化时返回 404。"""

    try:
        record = _service(http).load(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.model_dump(mode="json")
