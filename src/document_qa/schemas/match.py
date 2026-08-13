"""区域匹配与结构化差异模型。"""

from pydantic import Field

from document_qa.schemas.common import SchemaModel


class MatchMetrics(SchemaModel):
    """记录区域匹配的各项可解释指标。"""

    position_similarity: float = Field(ge=0, le=1)
    size_similarity: float = Field(ge=0, le=1)
    type_similarity: float = Field(ge=0, le=1)
    order_similarity: float = Field(ge=0, le=1)


class RegionMatch(SchemaModel):
    """表示源区域与目标区域的一对一匹配。"""

    page: int = Field(ge=1)
    source_region_id: str = Field(min_length=1)
    target_region_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    metrics: MatchMetrics


class StructuredDiff(SchemaModel):
    """保存匹配区域之间可供规则引擎使用的数值差异。"""

    page: int = Field(ge=1)
    source_region_id: str = Field(min_length=1)
    target_region_id: str = Field(min_length=1)
    x_shift_ratio: float
    y_shift_ratio: float
    width_change_ratio: float
    height_change_ratio: float
    font_size_change_ratio: float | None = None
    alignment_changed: bool = False
    color_changed: bool = False


class PageMatchResult(SchemaModel):
    """汇总一页中的成功匹配和未匹配区域。"""

    page: int = Field(ge=1)
    matches: list[RegionMatch] = Field(default_factory=list)
    diffs: list[StructuredDiff] = Field(default_factory=list)
    unmatched_source_region_ids: list[str] = Field(default_factory=list)
    unmatched_target_region_ids: list[str] = Field(default_factory=list)

