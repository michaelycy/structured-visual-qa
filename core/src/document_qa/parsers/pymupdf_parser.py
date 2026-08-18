"""使用 PyMuPDF 将 PDF 转换为统一文档模型。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import pymupdf

from document_qa.parsers.base import DocumentParsingError
from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    Document,
    ElementType,
    Page,
    TextStyle,
)


class PyMuPDFParser:
    """提取 PDF 页面中的文本 Span、图片、坐标和基础样式。"""

    def __init__(
        self,
        *,
        max_file_size: int = 100 * 1024 * 1024,
        max_pages: int = 500,
    ) -> None:
        """设置输入文件大小和页数上限，避免异常文档无限消耗资源。"""

        self.max_file_size = max_file_size
        self.max_pages = max_pages

    def parse(self, path: Path, document_id: str | None = None) -> Document:
        """解析 PDF，并确保对外结果不包含任何 PyMuPDF 运行时对象。"""

        safe_path = self._validate_path(path)
        resolved_document_id = document_id or self._hash_file(safe_path)

        try:
            with pymupdf.open(safe_path) as pdf:
                if pdf.needs_pass:
                    raise DocumentParsingError("不支持未解密的受密码保护 PDF")
                if pdf.page_count > self.max_pages:
                    raise DocumentParsingError(
                        f"PDF 页数 {pdf.page_count} 超过限制 {self.max_pages}"
                    )
                pages = [
                    self._parse_page(pdf_page, resolved_document_id)
                    for pdf_page in pdf
                ]
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"PDF 解析失败: {exc}") from exc

        return Document(
            document_id=resolved_document_id,
            source_path=str(safe_path),
            pages=pages,
            metadata={"parser": "pymupdf", "page_count": len(pages)},
        )

    def _validate_path(self, path: Path) -> Path:
        """验证输入路径、扩展名和大小，不接受目录或非 PDF 文件。"""

        safe_path = path.expanduser().resolve()
        if not safe_path.is_file():
            raise DocumentParsingError(f"PDF 文件不存在: {safe_path}")
        if safe_path.suffix.lower() != ".pdf":
            raise DocumentParsingError("只支持 .pdf 文件")
        file_size = safe_path.stat().st_size
        if file_size > self.max_file_size:
            raise DocumentParsingError(
                f"PDF 大小 {file_size} 字节超过限制 {self.max_file_size}"
            )
        return safe_path

    @staticmethod
    def _hash_file(path: Path) -> str:
        """流式计算文件摘要，生成稳定且不暴露文件名的文档 ID。"""

        digest = sha256()
        with path.open("rb") as file_handle:
            while chunk := file_handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _parse_page(self, pdf_page: pymupdf.Page, document_id: str) -> Page:
        """把一页 PDF 的原始字典转换为 Block 列表。"""

        page_number = pdf_page.number + 1
        raw_page = pdf_page.get_text("dict")
        blocks: list[Block] = []

        for block_index, raw_block in enumerate(raw_page.get("blocks", [])):
            block_type = raw_block.get("type")
            if block_type == 0:
                blocks.extend(
                    self._parse_text_block(raw_block, page_number, block_index)
                )
            elif block_type == 1:
                image_block = self._parse_image_block(
                    raw_block, page_number, block_index
                )
                if image_block is not None:
                    blocks.append(image_block)

        return Page(
            document_id=document_id,
            page=page_number,
            width=float(pdf_page.rect.width),
            height=float(pdf_page.rect.height),
            blocks=blocks,
            metadata={"rotation": int(pdf_page.rotation)},
        )

    def _parse_text_block(
        self,
        raw_block: dict[str, Any],
        page_number: int,
        block_index: int,
    ) -> list[Block]:
        """按 Span 建立文本 Block，以保留字体和局部边界框变化。"""

        blocks: list[Block] = []
        for line_index, line in enumerate(raw_block.get("lines", [])):
            for span_index, span in enumerate(line.get("spans", [])):
                bbox = self._build_bbox(span.get("bbox"))
                if bbox is None:
                    continue
                flags = int(span.get("flags", 0))
                block_id = (
                    f"p{page_number}-b{block_index}-l{line_index}-s{span_index}"
                )
                blocks.append(
                    Block(
                        id=block_id,
                        page=page_number,
                        type=ElementType.TEXT,
                        bbox=bbox,
                        style=TextStyle(
                            font_family=span.get("font"),
                            font_size=self._positive_float(span.get("size")),
                            # PyMuPDF 的字体 flags 中第 5 位表示粗体，第 2 位表示斜体。
                            font_weight=700 if flags & 16 else 400,
                            italic=bool(flags & 2),
                            color=self._format_color(span.get("color")),
                        ),
                        content=Content(text=span.get("text", "")),
                        metadata={
                            "source_block_index": block_index,
                            "source_line_index": line_index,
                            "source_span_index": span_index,
                        },
                    )
                )
        return blocks

    def _parse_image_block(
        self,
        raw_block: dict[str, Any],
        page_number: int,
        block_index: int,
    ) -> Block | None:
        """记录图片位置和可序列化属性，不把图片二进制写入模型。"""

        bbox = self._build_bbox(raw_block.get("bbox"))
        if bbox is None:
            return None
        extension = raw_block.get("ext")
        return Block(
            id=f"p{page_number}-b{block_index}-image",
            page=page_number,
            type=ElementType.IMAGE,
            bbox=bbox,
            content=Content(asset_ref=f"block-{block_index}.{extension or 'bin'}"),
            metadata={
                "source_block_index": block_index,
                "width": raw_block.get("width"),
                "height": raw_block.get("height"),
                "extension": extension,
            },
        )

    @staticmethod
    def _build_bbox(raw_bbox: Any) -> BoundingBox | None:
        """把 PyMuPDF 的 x0/y0/x1/y1 转换为项目的 x/y/width/height。"""

        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
            return None
        x0, y0, x1, y1 = (float(value) for value in raw_bbox)
        width = x1 - x0
        height = y1 - y0
        # 空 Span 可能产生零面积框；它们不具备布局比较价值，因此直接忽略。
        if width <= 0 or height <= 0:
            return None
        return BoundingBox(x=x0, y=y0, width=width, height=height)

    @staticmethod
    def _positive_float(value: Any) -> float | None:
        """只返回可用于样式比较的正数。"""

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @staticmethod
    def _format_color(value: Any) -> str | None:
        """把 PyMuPDF 的整数 RGB 颜色转换为稳定的十六进制字符串。"""

        if not isinstance(value, int):
            return None
        return f"#{value & 0xFFFFFF:06X}"

