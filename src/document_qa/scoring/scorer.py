"""根据问题严重度计算分数和状态。"""

from collections import defaultdict

from document_qa.config import QAThresholds
from document_qa.schemas import Issue, IssueType, QAStatus, Severity


class QAScorer:
    """将 Issue 列表转换为相互独立的 Score 和 Status。"""

    def __init__(self, thresholds: QAThresholds | None = None) -> None:
        """初始化评分阈值和各严重度扣分。"""

        self.thresholds = thresholds or QAThresholds()

    def score(self, issues: list[Issue]) -> tuple[float, QAStatus]:
        """累计扣分，并让 Critical/High 问题覆盖单纯的平均分结果。"""

        deductions_by_type: dict[IssueType, float] = defaultdict(float)
        for issue in issues:
            deductions_by_type[issue.type] += self.thresholds.severity_deductions[
                issue.severity
            ]
        # 图表标签、脚注等经常被拆成多个 Region；页内同类问题设置上限，
        # 防止同一视觉缺陷因解析粒度不同而被重复扣分到 0。
        deductions = sum(
            min(total, self.thresholds.issue_type_deduction_caps[issue_type])
            for issue_type, total in deductions_by_type.items()
        )
        score = max(0.0, 100.0 - deductions)
        severities = {issue.severity for issue in issues}

        if Severity.CRITICAL in severities or score < self.thresholds.fail_score:
            status = QAStatus.FAIL
        elif Severity.HIGH in severities or score < self.thresholds.pass_score:
            status = QAStatus.REVIEW
        else:
            status = QAStatus.PASS
        return score, status
