"""术语库路由：默认值、列表、读取、保存、删除。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from document_qa_server.services import GlossaryService

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


def _service(http: Request) -> GlossaryService:
    """从应用状态取术语库服务实例。"""

    return http.app.state.glossaries


@router.get("/default")
def get_default(http: Request) -> dict:
    """返回内置示例术语库，作为界面初始值。"""

    return _service(http).default().model_dump(mode="json")


@router.get("/list")
def list_glossaries(http: Request) -> dict:
    """列出服务器上已保存的术语库摘要。"""

    summaries = _service(http).list()
    return {
        "glossaries": [
            {
                "filename": item.filename,
                "glossary_id": item.glossary_id,
                "name": item.name,
                "version": item.version,
                "entry_count": item.entry_count,
                "reference": item.reference,
            }
            for item in summaries
        ]
    }


@router.get("/item/{filename}")
def get_glossary(filename: str, http: Request) -> dict:
    """读取单个术语库完整内容。"""

    try:
        glossary = _service(http).get(filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return glossary.model_dump(mode="json")


class GlossarySaveRequest(BaseModel):
    """界面提交的完整术语库对象。"""

    glossary: dict


@router.post("/save")
def save_glossary(request: GlossarySaveRequest, http: Request) -> dict:
    """校验并保存术语库。"""

    try:
        path, reference = _service(http).save(request.glossary)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path), "reference": reference}


@router.delete("/item/{filename}")
def delete_glossary(filename: str, http: Request) -> dict:
    """删除已保存术语库。"""

    try:
        _service(http).delete(filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": filename}
