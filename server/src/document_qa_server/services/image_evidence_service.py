"""质检记录图片证据服务。"""

from __future__ import annotations

import re
from pathlib import Path

from document_qa.parsers import DocumentParsingError, PyMuPDFParser

from document_qa_server.services.history_service import CompareHistoryService

_REGION_ID_PATTERN = re.compile(r"^p(?P<page>[1-9]\d*)-r(?P<block>\d+)(?:-c[1-9]\d*)?$")


class ImageEvidenceService:
    """按历史记录与 Region ID 提取受控的 PDF 内嵌图片证据。"""

    def __init__(self, history: CompareHistoryService) -> None:
        """注入历史记录服务，禁止客户端直接指定文件路径。"""

        self._history = history
        self._parser = PyMuPDFParser()

    def get(self, record_id: str, side: str, region_id: str) -> tuple[bytes, str]:
        """读取记录指定侧的图片 Region，返回图片字节和 MIME 类型。"""

        if side not in {"source", "target"}:
            raise ValueError(f"无效文档侧: {side}")
        match = _REGION_ID_PATTERN.fullmatch(region_id)
        if match is None:
            raise ValueError(f"无效图片区域 ID: {region_id}")

        record = self._history.get(record_id)
        raw_path = record.source_path if side == "source" else record.target_path
        if not raw_path:
            raise ValueError("质检记录缺少原始文档路径")
        try:
            return self._parser.extract_image_block(
                Path(raw_path),
                page=int(match.group("page")),
                block_index=int(match.group("block")),
            )
        except DocumentParsingError as exc:
            raise ValueError(str(exc)) from exc
