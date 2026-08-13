"""解析文档的几何、样式及其他共享模型。"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchemaModel(BaseModel):
    """所有公开 Schema 共用的严格基础模型。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ElementType(StrEnum):
    """项目能够识别和比较的文档元素类型。"""

    TEXT = "text"
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST = "list"
    IMAGE = "image"
    TABLE = "table"
    CHART = "chart"
    SHAPE = "shape"
    HEADER = "header"
    FOOTER = "footer"
    OTHER = "other"


class HorizontalAlignment(StrEnum):
    """文本区域支持的水平对齐方式。"""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"
    OTHER = "other"


class BoundingBox(SchemaModel):
    """文档坐标矩形；允许 x/y 越界，以便检测器记录异常。"""

    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)

    @field_validator("x", "y", "width", "height")
    @classmethod
    def values_must_be_finite(cls, value: float) -> float:
        """拒绝无法稳定序列化和比较的无穷值与 NaN。"""

        if not isfinite(value):
            raise ValueError("bounding box values must be finite")
        return value

    @property
    def right(self) -> float:
        """返回矩形右边界坐标。"""

        return self.x + self.width

    @property
    def bottom(self) -> float:
        """返回矩形下边界坐标。"""

        return self.y + self.height

    @property
    def area(self) -> float:
        """返回矩形面积。"""

        return self.width * self.height


class TextStyle(SchemaModel):
    """保存跨文档比较所需的基础文字样式。"""

    font_family: str | None = None
    font_size: float | None = Field(default=None, gt=0)
    font_weight: int | None = Field(default=None, ge=1, le=1000)
    italic: bool | None = None
    color: str | None = None
    alignment: HorizontalAlignment | None = None
    line_height: float | None = Field(default=None, gt=0)


class Content(SchemaModel):
    """保存文本内容、语言或外部资源引用。"""

    text: str | None = None
    language: str | None = None
    asset_ref: str | None = None


class RegionRelationships(SchemaModel):
    """保存 Region 与直接邻近 Region 的引用关系。"""

    above: str | None = None
    below: str | None = None
    left_of: str | None = None
    right_of: str | None = None


Metadata = dict[str, Any]
