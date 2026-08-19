"""比较任务路由：双模式（异步默认）提交 + 任务轮询。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from document_qa.parsers import DocumentParsingError
from document_qa.profiles import default_rule_profile
from document_qa_server.api.dto import CompareRequest
from document_qa_server.services import (
    CompareService,
    GlossaryService,
    NormalizationError,
    ProfileService,
)
from document_qa_server.services.file_service import ACCEPTED_SUFFIXES

router = APIRouter(prefix="/api", tags=["compare"])


def _resolve_document(value: str, label: str) -> Path:
    """校验输入是存在的本地文档（PDF 或可归一化 Office 格式）。"""

    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in ACCEPTED_SUFFIXES:
        raise HTTPException(
            status_code=400, detail=f"无效{label}文档路径: {path}"
        )
    return path


def _load_glossary(request: CompareRequest, http: Request):
    """加载可选术语库；引用非法或不存在时返回 400。"""

    if not request.glossary_reference:
        return None
    service: GlossaryService = http.app.state.glossaries
    try:
        return service.load_by_reference(request.glossary_reference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _load_profile(request: CompareRequest, http: Request):
    """加载可选 Profile；路径存在但校验失败时返回 400。"""

    if not request.profile_path:
        return default_rule_profile()
    profile_service: ProfileService = http.app.state.profiles
    try:
        return profile_service.load(Path(request.profile_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _history_writer(http: Request):
    """构造历史记录回调：返回 record_id 供任务状态回查。"""

    def write(report_dict, source, target, s_display, t_display) -> str:
        record = http.app.state.history.add(
            report=report_dict,
            source_path=str(source),
            target_path=str(target),
            source_display=s_display,
            target_display=t_display,
        )
        return record.record_id

    return write


@router.post("/compare")
def compare(request: CompareRequest, http: Request, background: BackgroundTasks) -> dict:
    """提交比较任务。

    异步模式（默认）：立即返回 task_id，前端轮询 /api/tasks/{id}；
    同步模式（DQA_ASYNC_MODE=false）：阻塞执行并直接返回报告。
    """

    service: CompareService = http.app.state.compare
    source = _resolve_document(request.source, "源")
    target = _resolve_document(request.target, "目标")
    profile = _load_profile(request, http)
    glossary = _load_glossary(request, http)

    if not http.app.state.async_mode:
        # 同步回归路径：行为与历史版本完全一致。
        try:
            report, rendered = service.run(
                source,
                target,
                profile=profile,
                glossary=glossary,
                render=request.render,
                render_scope=request.render_scope,
            )
        except DocumentParsingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except NormalizationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        record = http.app.state.history.add(
            report=report.model_dump(mode="json"),
            source_path=str(source),
            target_path=str(target),
            source_display=request.source_display or source.name,
            target_display=request.target_display or target.name,
        )
        return {
            "task_id": None,
            "report": report.model_dump(mode="json"),
            "rendered": rendered,
        }

    task_id = service.submit(
        source,
        target,
        displays=(
            request.source_display or source.name,
            request.target_display or target.name,
        ),
    )
    background.add_task(
        service.execute,
        task_id,
        source,
        target,
        profile=profile,
        glossary=glossary,
        render=request.render,
        render_scope=request.render_scope,
        history_callback=_history_writer(http),
    )
    return {"task_id": task_id, "status": "queued"}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, http: Request) -> dict:
    """轮询比较任务状态；done 时附带报告与渲染索引。"""

    task = http.app.state.compare.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return {
        "task_id": task_id,
        "status": task.status,
        "error": task.error,
        "report": task.report,
        "rendered": task.rendered,
        "history_record_id": task.history_record_id,
    }
