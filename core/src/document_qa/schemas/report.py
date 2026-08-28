"""QA 页面结果与文档报告模型。"""

from enum import StrEnum

from pydantic import Field

from document_qa.schemas.common import SchemaModel
from document_qa.schemas.issue import Issue
from document_qa.schemas.match import RegionMatch, StructuredDiff
from document_qa.profiles import RuleProfile


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
    # 旧报告没有该字段，读取边界会从完整 Issue 明细兼容计算。
    problem_total: int | None = Field(default=None, ge=0)


class QAReport(SchemaModel):
    """一次源文档与目标文档比较的最终结果。"""

    source_document_id: str = Field(min_length=1)
    target_document_id: str = Field(min_length=1)
    rule_profile_reference: str = Field(min_length=1)
    rule_profile_snapshot: RuleProfile
    document_score: float = Field(ge=0, le=100)
    status: QAStatus
    summary: ReportSummary
    pages: list[PageQAResult] = Field(default_factory=list)
    # 执行环境备注（如归一化来源），不影响评分与状态。
    metadata: dict[str, "str | list | dict | None"] = Field(default_factory=dict)
