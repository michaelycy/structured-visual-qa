"""集中维护匹配、检测和评分阈值。"""

from dataclasses import dataclass, field

from document_qa.schemas import IssueType, Severity


@dataclass(frozen=True, slots=True)
class QAThresholds:
    """保存可通过 Golden Sample 校准的默认规则阈值。"""

    minimum_match_score: float = 0.45
    shifted_ratio: float = 0.05
    severely_shifted_ratio: float = 0.15
    font_shrink_ratio: float = -0.20
    critical_font_shrink_ratio: float = -0.35
    overlap_ratio: float = 0.05
    overlap_increase_ratio: float = 0.05
    merged_text_coverage_ratio: float = 0.40
    image_caption_area_ratio: float = 0.005
    pass_score: float = 90.0
    fail_score: float = 75.0
    severity_deductions: dict[Severity, float] = field(
        default_factory=lambda: {
            Severity.INFO: 0.0,
            Severity.LOW: 1.0,
            Severity.MEDIUM: 4.0,
            Severity.HIGH: 10.0,
            Severity.CRITICAL: 25.0,
        }
    )
    issue_type_deduction_caps: dict[IssueType, float] = field(
        default_factory=lambda: {
            IssueType.REGION_SHIFTED: 12.0,
            IssueType.TEXT_OVERFLOW: 25.0,
            IssueType.TEXT_CLIPPED: 25.0,
            IssueType.ABNORMAL_WRAP: 10.0,
            IssueType.LINE_COUNT_EXPLOSION: 10.0,
            IssueType.FONT_SHRINK: 10.0,
            IssueType.TEXT_OVERLAP: 10.0,
            IssueType.TEXT_IMAGE_OVERLAP: 25.0,
            IssueType.CONTENT_OUT_OF_PAGE: 25.0,
            IssueType.MISSING_ELEMENT: 10.0,
            IssueType.ADDED_ELEMENT: 3.0,
            IssueType.MISSING_IMAGE: 25.0,
            IssueType.TYPOGRAPHY_CHANGED: 10.0,
            IssueType.TABLE_STRUCTURE_CHANGED: 25.0,
            IssueType.PAGE_MISSING: 25.0,
            IssueType.OTHER: 10.0,
        }
    )
