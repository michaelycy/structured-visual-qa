"""Profile 配置路由：默认值、JSON Schema 与保存。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from document_qa_server.api.dto import ProfileSaveRequest
from document_qa_server.services import ProfileService

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/default")
def get_default_profile(http: Request) -> dict:
    """返回内置平衡配置，作为配置表单的初始值。"""

    service: ProfileService = http.app.state.profiles
    return service.default().model_dump(mode="json")


@router.get("/schema")
def get_profile_schema(http: Request) -> dict:
    """返回 Profile JSON Schema，供前端动态生成表单和校验。"""

    service: ProfileService = http.app.state.profiles
    return service.schema()


@router.post("/save")
def save_profile(request: ProfileSaveRequest, http: Request) -> dict:
    """校验并保存界面编辑的 Profile，返回服务端存储路径。"""

    service: ProfileService = http.app.state.profiles
    try:
        path, reference = service.save(request.profile)
    except Exception as exc:
        # pydantic 校验失败与非法文件名统一转 400，附具体原因。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path), "reference": reference}
