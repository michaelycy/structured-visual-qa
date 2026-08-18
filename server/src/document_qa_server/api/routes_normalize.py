"""归一化能力路由：格式支持探测。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from document_qa_server.services import NormalizationService

router = APIRouter(prefix="/api/normalize", tags=["normalize"])


@router.get("/status")
def normalization_status(http: Request) -> dict:
    """报告支持的归一化格式与 LibreOffice 引擎可用性。

    引擎缺失时前端应禁用 Office 上传并展示安装指引。
    """

    service: NormalizationService = http.app.state.normalizer
    engine = NormalizationService.check_engine()
    return {
        "supported_extensions": NormalizationService.supported_extensions(),
        "engine_available": engine is not None,
        "engine_version": engine,
    }
