"""根据问题严重度计算分数和状态。"""

from document_qa.config import QAThresholds
from document_qa.schemas import Issue, QAStatus, Severity


class QAScorer:
    """将 Issue 列表转换为相互独立的 Score 和 Status。"""

    def __init__(self, thresholds: QAThresholds | None = None) -> None:
        """初始化评分阈值和各严重度扣分。"""

        self.thresholds = thresholds or QAThresholds()

    def score(self, issues: list[Issue]) -> tuple[float, QAStatus]:
        """累计扣分，并让 Critical/High 问题覆盖单纯的平均分结果。"""

        deductions = sum(
            self.thresholds.severity_deductions[issue.severity] for issue in issues
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

