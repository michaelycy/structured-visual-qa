"""Profile 配置路由：默认值、JSON Schema、列表与生命周期管理。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from document_qa_server.api.dto import ProfileSaveRequest
from document_qa_server.services import ProfileService

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _service(http: Request) -> ProfileService:
    """从应用状态取 Profile 服务实例。"""

    return http.app.state.profiles


@router.get("/default")
def get_default_profile(http: Request) -> dict:
    """返回内置平衡配置，作为配置表单的初始值。"""

    return _service(http).default().model_dump(mode="json")


@router.get("/schema")
def get_profile_schema(http: Request) -> dict:
    """返回 Profile JSON Schema，供前端动态生成表单和校验。"""

    return _service(http).schema()


@router.get("/list")
def list_profiles(http: Request) -> dict:
    """列出服务器上已保存的全部 Profile 摘要。"""

    summaries = _service(http).list()
    return {
        "profiles": [
            {
                "filename": item.filename,
                "profile_id": item.profile_id,
                "name": item.name,
                "version": item.version,
                "status": item.status,
                "reference": item.reference,
            }
            for item in summaries
        ]
    }


@router.get("/item/{filename}")
def get_profile(filename: str, http: Request) -> dict:
    """读取单个已保存 Profile 的完整配置。"""

    try:
        profile = _service(http).get(filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return profile.model_dump(mode="json")


@router.delete("/item/{filename}")
def delete_profile(filename: str, http: Request) -> dict:
    """归档已保存 Profile。"""

    try:
        _service(http).delete(filename)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": filename}


@router.post("/item/{filename}/publish")
def publish_profile(filename: str, http: Request) -> dict:
    """发布草稿 Profile，发布后同版本不可覆盖。"""

    try:
        summary = _service(http).publish(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "filename": summary.filename,
        "reference": summary.reference,
        "status": summary.status,
    }


@router.post("/save")
def save_profile(request: ProfileSaveRequest, http: Request) -> dict:
    """校验并保存界面编辑的 Profile，返回服务端存储路径。"""

    try:
        path, reference = _service(http).save(request.profile)
    except Exception as exc:
        # pydantic 校验失败与非法文件名统一转 400，附具体原因。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path), "reference": reference}
