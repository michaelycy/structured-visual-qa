"""样本管理路由：创建、列表、编辑、归档与工作台载入。"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from document_qa_server.services import BuiltinSampleScanResult, FileService, SampleService

router = APIRouter(prefix="/api/samples", tags=["samples"])


class SampleUpdateRequest(BaseModel):
    """用户可编辑的样本元数据。"""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    source_language: str = Field(default="und", min_length=2, max_length=35)
    target_language: str = Field(default="und", min_length=2, max_length=35)


def _service(http: Request) -> SampleService:
    """从应用状态取得样本服务。"""

    return http.app.state.samples


def _payload(record) -> dict:
    """把服务模型转换为不隐藏路径的本机工作台 DTO。"""

    return record.__dict__


def _scan_payload(result: BuiltinSampleScanResult) -> dict:
    """把扫描结果转换为稳定的 JSON 摘要。"""

    return {
        "discovered": result.discovered,
        "created": result.created,
        "existing": result.existing,
        "conflict_count": len(result.conflicts),
        "conflicts": list(result.conflicts),
    }


@router.get("")
def list_samples(http: Request, include_archived: bool = False) -> dict:
    """返回样本列表；默认不含归档样本。"""

    return {
        "samples": [
            _payload(item)
            for item in _service(http).list(include_archived=include_archived)
        ]
    }


@router.post("/rescan")
def rescan_builtin_samples(http: Request) -> dict:
    """重新扫描内置样本目录，并返回新增、已有与冲突摘要。"""

    try:
        return _scan_payload(_service(http).rescan_builtins())
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{sample_id}")
def get_sample(sample_id: str, http: Request) -> dict:
    """读取单个样本详情。"""

    try:
        return _payload(_service(http).get(sample_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("")
async def create_sample(
    http: Request,
    name: str = Form(...),
    description: str = Form(""),
    source_language: str = Form("und"),
    target_language: str = Form("und"),
    source: UploadFile = ...,
    target: UploadFile = ...,
) -> dict:
    """流式保存两侧文档并创建一个用户样本对。"""

    files: FileService = http.app.state.files
    try:
        source_path = await files.save_upload_stream(
            source.filename or "source.pdf", source
        )
        target_path = await files.save_upload_stream(
            target.filename or "target.pdf", target
        )
        record = _service(http).create(
            name=name,
            description=description,
            source_path=source_path,
            source_name=source.filename or source_path.name,
            target_path=target_path,
            target_name=target.filename or target_path.name,
            source_language=source_language,
            target_language=target_language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _payload(record)


@router.patch("/{sample_id}")
def update_sample(
    sample_id: str, request: SampleUpdateRequest, http: Request
) -> dict:
    """修改用户样本名称、描述和语言对。"""

    try:
        return _payload(
            _service(http).update(
                sample_id,
                name=request.name,
                description=request.description,
                source_language=request.source_language,
                target_language=request.target_language,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{sample_id}")
def archive_sample(sample_id: str, http: Request) -> dict:
    """归档用户样本，不删除文件和历史记录。"""

    try:
        _service(http).archive(sample_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"archived": sample_id}


@router.post("/{sample_id}/use")
def use_sample(sample_id: str, http: Request) -> dict:
    """校验样本文件存在并返回工作台所需的源、目标引用。"""

    try:
        return _payload(_service(http).use(sample_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
