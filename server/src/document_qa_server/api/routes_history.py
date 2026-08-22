"""对比记录路由：历史列表与单条读取。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from document_qa_server.services import CompareHistoryService, ImageEvidenceService

router = APIRouter(prefix="/api/history", tags=["history"])


def _service(http: Request) -> CompareHistoryService:
    """从应用状态取历史服务实例。"""

    return http.app.state.history


def _image_service(http: Request) -> ImageEvidenceService:
    """从应用状态取图片证据服务实例。"""

    return http.app.state.image_evidence


@router.get("/list")
def list_history(http: Request) -> dict:
    """按时间倒序列出对比记录摘要。"""

    records = _service(http).list()
    return {
        "records": [
            {
                "record_id": item.record_id,
                "created_at": item.created_at,
                "source_display": item.source_display,
                "target_display": item.target_display,
                "status": item.status,
                "document_score": item.document_score,
                "pages": item.pages,
                "issue_total": item.issue_total,
                "rule_profile_reference": item.rule_profile_reference,
                "normalized_from": item.normalized_from,
            }
            for item in records
        ]
    }


@router.get("/item/{record_id}")
def get_history(record_id: str, http: Request) -> dict:
    """读取单条完整记录（含报告），供界面重新查看。"""

    try:
        record = _service(http).get(record_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@router.get("/item/{record_id}/image/{side}/{region_id}")
def get_history_image(
    record_id: str,
    side: str,
    region_id: str,
    http: Request,
) -> Response:
    """返回 Issue 对应 PDF 图片 Region 的内嵌原图。"""

    try:
        content, media_type = _image_service(http).get(record_id, side, region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
