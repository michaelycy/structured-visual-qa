"""集中维护匹配、检测和评分阈值。"""

from dataclasses import dataclass, field

from document_qa.schemas import Severity


@dataclass(frozen=True, slots=True)
class QAThresholds:
    """保存可通过 Golden Sample 校准的默认规则阈值。"""

    minimum_match_score: float = 0.45
    shifted_ratio: float = 0.05
    severely_shifted_ratio: float = 0.15
    font_shrink_ratio: float = -0.20
    critical_font_shrink_ratio: float = -0.35
    overlap_ratio: float = 0.05
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

