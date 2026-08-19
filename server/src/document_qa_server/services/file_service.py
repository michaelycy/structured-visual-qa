"""文件服务：处理界面上传的 PDF/Office 文档与服务器样例文件列表。"""

from __future__ import annotations

import os
import shutil
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Protocol

MAX_UPLOAD_BYTES = 100 * 1024 * 1024

# 上传直接受的格式：PDF 加可归一化的 Office 格式（转换在比较时进行）。
from document_qa_server.services.normalization_service import (
    SUPPORTED_FORMATS,
    matches_magic,
)

ACCEPTED_SUFFIXES = (".pdf", *sorted(SUPPORTED_FORMATS))


class _AsyncReader(Protocol):
    """带异步分块读取的最小字节流协议（FastAPI UploadFile 满足）。"""

    async def read(self, size: int) -> bytes: ...


class FileService:
    """封装上传文件的落盘与样例目录枚举。"""

    def __init__(
        self,
        *,
        artifacts_dir: Path,
        samples_dir: Path,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
    ) -> None:
        """注入产物根目录、样例目录与上传大小上限（默认 100 MiB）。"""

        self._uploads_dir = artifacts_dir / "uploads"
        self._samples_dir = samples_dir
        self.max_upload_bytes = max_upload_bytes

    async def save_upload_stream(self, filename: str, stream: _AsyncReader) -> Path:
        """流式校验并保存上传文件，返回服务器端路径。

        边读边写临时文件并累计哈希与大小，避免整份文件缓冲进内存；
        内容头部（PDF 的 %PDF、Office 的魔数）在落盘后即时校验，不符即删除。
        以内容摘要做文件名前缀，同一文件重复上传自然去重；文件名只用于
        展示，不参与路径拼接（契约 §9 输入安全）。
        """

        suffix = Path(filename).suffix.lower()
        if suffix not in ACCEPTED_SUFFIXES:
            raise ValueError(
                f"只接受 PDF 或可归一化的 Office 格式: {', '.join(ACCEPTED_SUFFIXES)}"
            )
        self._uploads_dir.mkdir(parents=True, exist_ok=True)

        digest = sha256()
        head = b""
        total = 0
        temp_fd, temp_path = tempfile.mkstemp(dir=self._uploads_dir, suffix=".part")
        try:
            with os.fdopen(temp_fd, "wb") as output:
                while chunk := await stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > self.max_upload_bytes:
                        raise ValueError(
                            f"文件大小超过 {self.max_upload_bytes // (1024 * 1024)} MiB 限制"
                        )
                    digest.update(chunk)
                    if len(head) < 8:
                        head = (head + chunk)[:8]
                    output.write(chunk)
            self._validate_content(suffix, head)
        except BaseException:
            Path(temp_path).unlink(missing_ok=True)
            raise

        safe_name = self._safe_filename(filename)
        path = self._uploads_dir / f"{digest.hexdigest()[:16]}-{safe_name}"
        os.replace(temp_path, path)
        return path

    def _validate_content(self, suffix: str, head: bytes) -> None:
        """校验上传内容头部与扩展名一致，防止任意文件改名混入。"""

        if suffix == ".pdf":
            if not head.startswith(b"%PDF"):
                raise ValueError("不是有效的 PDF 文件")
            return
        if not matches_magic(suffix, head):
            raise ValueError(f"文件内容与扩展名不符: {suffix}")

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """去掉路径分隔符；文件名只用于展示与去重命名。"""

        return filename.replace("/", "_").replace("\\", "_")

    def copy_sample(self, name: str) -> Path:
        """把样例目录中的文件复制为可比较输入，返回副本路径。

        样例库保持只读；比较任务的所有产物都进 webapp-artifacts/。
        """

        if "/" in name or "\\" in name or not name.lower().endswith(".pdf"):
            raise ValueError("无效样例文件名")
        source = self._samples_dir / name
        if not source.is_file():
            raise ValueError(f"样例不存在: {name}")
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        target = self._uploads_dir / f"sample-{name}"
        shutil.copyfile(source, target)
        return target

    def list_samples(self) -> list[str]:
        """列出样例目录中的 PDF 文件名，供前端下拉选择。"""

        if not self._samples_dir.is_dir():
            return []
        return sorted(path.name for path in self._samples_dir.glob("*.pdf"))
