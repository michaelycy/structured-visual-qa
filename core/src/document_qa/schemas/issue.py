"""统一 QA 问题模型。"""

from enum import StrEnum
from typing import Any

from pydantic import Field

from document_qa.schemas.common import BoundingBox, SchemaModel


class Severity(StrEnum):
    """问题对文档交付质量的影响等级。"""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueType(StrEnum):
    """规则检测器和视觉复核器共用的问题类型。"""

    REGION_SHIFTED = "region_shifted"
    REGION_RESIZED = "region_resized"
    TEXT_FRAGMENTED = "text_fragmented"
    TEXT_OVERFLOW = "text_overflow"
    TEXT_CLIPPED = "text_clipped"
    ABNORMAL_WRAP = "abnormal_wrap"
    LINE_COUNT_EXPLOSION = "line_count_explosion"
    FONT_SHRINK = "font_shrink"
    TEXT_OVERLAP = "text_overlap"
    TEXT_IMAGE_OVERLAP = "text_image_overlap"
    CONTENT_OUT_OF_PAGE = "content_out_of_page"
    MISSING_ELEMENT = "missing_element"
    ADDED_ELEMENT = "added_element"
    MISSING_IMAGE = "missing_image"
    TYPOGRAPHY_CHANGED = "typography_changed"
    TABLE_STRUCTURE_CHANGED = "table_structure_changed"
    PAGE_MISSING = "page_missing"
    NUMBER_MISMATCH = "number_mismatch"
    UNTRANSLATED_TEXT = "untranslated_text"
    GLOSSARY_VIOLATION = "glossary_violation"
    INVISIBLE_TEXT = "invisible_text"
    TEXT_VECTORIZED = "text_vectorized"
    TEXT_ALIGNMENT_CHANGED = "text_alignment_changed"
    OTHER = "other"


class Issue(SchemaModel):
    """检测器或复核器发现的页面级问题，可关联源/目标区域。"""

    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    type: IssueType
    severity: Severity
    source_region: str | None = None
    target_region: str | None = None
    bbox: BoundingBox | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(min_length=1)
    detector: str | None = None
