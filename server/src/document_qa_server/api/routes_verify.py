"""分阶段验证路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from document_qa_server.api.dto import VerifyRequest
from document_qa_server.api.routes_compare import _resolve_document
from document_qa_server.services import VerifyService
from document_qa.verify import Stage

router = APIRouter(prefix="/api", tags=["verify"])


@router.post("/verify")
def verify(request: VerifyRequest, http: Request) -> dict:
    """分阶段执行并返回各阶段摘要、数据与产物路径。"""

    service: VerifyService = http.app.state.verify
    source = _resolve_document(request.source, "源")
    target = _resolve_document(request.target, "目标")
    results = service.run(
        source, target, stop_after=Stage(request.stop_after)
    )
    return {
        "stages": [
            {
                "stage": item.stage,
                "summary": item.summary,
                "data": item.data,
                "artifact": item.artifact,
            }
            for item in results
        ]
    }
