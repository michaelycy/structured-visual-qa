"""文件服务：处理界面上传的 PDF/Office 文档与服务器样例文件列表。"""

from __future__ import annotations

import shutil
from hashlib import sha256
from pathlib import Path

MAX_UPLOAD_BYTES = 100 * 1024 * 1024

# 上传直接受的格式：PDF 加可归一化的 Office 格式（转换在比较时进行）。
from document_qa_server.services.normalization_service import SUPPORTED_FORMATS

ACCEPTED_SUFFIXES = (".pdf", *sorted(SUPPORTED_FORMATS))


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

    def save_upload(self, filename: str, content: bytes) -> Path:
        """校验并保存上传文件，返回服务器端路径。

        以内容摘要做文件名前缀，同一文件重复上传自然去重；
        文件名只用于展示，不参与路径拼接（契约 §9 输入安全）。
        """

        if filename.lower().endswith(ACCEPTED_SUFFIXES) is False:
            raise ValueError(
                f"只接受 PDF 或可归一化的 Office 格式: {', '.join(ACCEPTED_SUFFIXES)}"
            )
        if len(content) > self.max_upload_bytes:
            raise ValueError(
                f"文件大小超过 {self.max_upload_bytes // (1024 * 1024)} MiB 限制"
            )
        if filename.lower().endswith(".pdf") and not content.startswith(b"%PDF"):
            raise ValueError("不是有效的 PDF 文件")
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        digest = sha256(content).hexdigest()[:16]
        safe_name = filename.replace("/", "_").replace("\\", "_")
        path = self._uploads_dir / f"{digest}-{safe_name}"
        path.write_bytes(content)
        return path

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
