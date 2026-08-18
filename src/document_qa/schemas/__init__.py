"""对外公开的 Schema 导出。"""

from document_qa.schemas.block import Block
from document_qa.schemas.common import (
    BoundingBox,
    Content,
    ElementType,
    HorizontalAlignment,
    RegionRelationships,
    TEXT_TYPES,
    TextStyle,
)
from document_qa.schemas.document import Document
from document_qa.schemas.issue import Issue, IssueType, Severity
from document_qa.schemas.match import (
    MatchMetrics,
    PageMatchResult,
    RegionMatch,
    StructuredDiff,
)
from document_qa.schemas.page import Page
from document_qa.schemas.report import PageQAResult, QAReport, QAStatus, ReportSummary
from document_qa.schemas.region import Region

__all__ = [
    "Block",
    "BoundingBox",
    "Content",
    "Document",
    "ElementType",
    "HorizontalAlignment",
    "Issue",
    "IssueType",
    "MatchMetrics",
    "Page",
    "PageMatchResult",
    "PageQAResult",
    "QAReport",
    "QAStatus",
    "Region",
    "RegionRelationships",
    "Severity",
    "RegionMatch",
    "ReportSummary",
    "StructuredDiff",
    "TEXT_TYPES",
    "TextStyle",
]
