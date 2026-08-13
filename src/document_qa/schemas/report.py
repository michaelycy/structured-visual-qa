"""QA 页面结果与文档报告模型。"""

from enum import StrEnum

from pydantic import Field

from document_qa.schemas.common import SchemaModel
from document_qa.schemas.issue import Issue
from document_qa.schemas.match import RegionMatch, StructuredDiff


class QAStatus(StrEnum):
    """文档或页面的最终交付状态。"""

    PASS = "pass"
    REVIEW = "review"
    FAIL = "fail"


class PageQAResult(SchemaModel):
    """保存单页的匹配、差异、问题和评分。"""

    page: int = Field(ge=1)
    score: float = Field(ge=0, le=100)
    status: QAStatus
    matches: list[RegionMatch] = Field(default_factory=list)
    diffs: list[StructuredDiff] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)


class ReportSummary(SchemaModel):
    """提供前端和流水线使用的文档级统计。"""

    pages: int = Field(ge=0)
    passed_pages: int = Field(ge=0)
    review_pages: int = Field(ge=0)
    failed_pages: int = Field(ge=0)
    issue_counts: dict[str, int] = Field(default_factory=dict)


class QAReport(SchemaModel):
    """一次源文档与目标文档比较的最终结果。"""

    source_document_id: str = Field(min_length=1)
    target_document_id: str = Field(min_length=1)
    document_score: float = Field(ge=0, le=100)
    status: QAStatus
    summary: ReportSummary
    pages: list[PageQAResult] = Field(default_factory=list)

