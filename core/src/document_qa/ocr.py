"""可选 OCR 能力的核心协议与统一结果模型。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from document_qa.schemas.common import BoundingBox, SchemaModel


class OCRLine(SchemaModel):
    """一条 OCR 文字及其在输入图片像素坐标中的位置。"""

    text: str
    confidence: float = Field(ge=0, le=1)
    bbox: BoundingBox


class OCRResult(SchemaModel):
    """一次图片 OCR 的规范化结果，不保存输入图片或模型对象。"""

    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    lines: list[OCRLine] = Field(default_factory=list)


@runtime_checkable
class OCRProvider(Protocol):
    """OCR 适配器协议；具体框架由调用方注入。"""

    @property
    def provider_name(self) -> str:
        """返回适配器名称。"""

    @property
    def model_fingerprint(self) -> str:
        """返回可写入报告的模型与运行配置标识。"""

    def recognize(self, image_png: bytes) -> OCRResult:
        """识别一张内存 PNG，并返回统一结果。"""
