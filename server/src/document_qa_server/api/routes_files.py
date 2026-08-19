"""文件路由：PDF 上传与服务器样例列表。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from document_qa_server.services import FileService

router = APIRouter(prefix="/api/files", tags=["files"])


def _file_service(http: Request) -> FileService:
    """从应用状态取文件服务实例。"""

    return http.app.state.files


@router.get("/samples")
def list_samples(http: Request) -> dict:
    """返回服务器样例 PDF 文件名列表。"""

    return {"samples": _file_service(http).list_samples()}


@router.post("/sample")
def use_sample(name: str, http: Request) -> dict:
    """把样例文件复制为比较输入，返回服务器端路径。"""

    service = _file_service(http)
    try:
        path = service.copy_sample(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path), "name": name}


@router.post("/upload")
async def upload(file: UploadFile, http: Request) -> dict:
    """接收浏览器上传的文档并保存，返回服务器端路径。

    流式分块落盘（对抗审查 H-2：整读进内存后再校验大小，
    恶意大文件会在拒绝前耗尽内存）；累计超限即中止并清理。
    """

    service = _file_service(http)
    limit = service.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过 {limit // (1024 * 1024)} MiB 限制",
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    try:
        path = service.save_upload(file.filename or "upload.pdf", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path), "name": file.filename}
