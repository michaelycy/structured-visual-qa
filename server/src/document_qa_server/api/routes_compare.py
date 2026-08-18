"""比较任务路由：请求校验、服务调用与状态码映射。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from document_qa_server.api.dto import CompareRequest
from document_qa.parsers import DocumentParsingError
from document_qa_server.services import CompareService, ProfileService

router = APIRouter(prefix="/api", tags=["compare"])


def _resolve_pdf(value: str, label: str) -> Path:
    """校验输入是存在的本地 PDF 文件，错误信息与 CLI 对齐。"""

    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail=f"无效{label} PDF 路径: {path}")
    return path


@router.post("/compare")
def compare(request: CompareRequest, http: Request) -> dict:
    """执行完整比较，返回报告 JSON 与渲染页索引。"""

    service: CompareService = http.app.state.compare
    profile_service: ProfileService = http.app.state.profiles
    source = _resolve_pdf(request.source, "源")
    target = _resolve_pdf(request.target, "目标")

    profile = None
    if request.profile_path:
        try:
            profile = profile_service.load(Path(request.profile_path))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        report, rendered = service.run(
            source,
            target,
            profile=profile,
            render=request.render,
            render_scope=request.render_scope,
        )
    except DocumentParsingError as exc:
        # 引擎错误映射为 422：请求格式合法但引用的文档无法解析。
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"report": report.model_dump(mode="json"), "rendered": rendered}
