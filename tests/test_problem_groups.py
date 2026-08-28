"""问题组聚合回归测试。"""

import unittest

from document_qa.problem_groups import count_problem_groups
from document_qa.schemas import Issue, IssueType, PageQAResult, QAStatus, Severity


class ProblemGroupTests(unittest.TestCase):
    """验证规则命中明细与用户问题组计数相互独立。"""

    def test_groups_page_rasterization_and_ignores_blank_added_issue(self) -> None:
        """同页栅格化归为一组，空白新增区域不进入问题组。"""

        issues = [
            Issue(
                id=f"raster-{index}",
                page=1,
                type=IssueType.TEXT_RASTERIZED,
                severity=Severity.HIGH,
                source_region=f"source-{index}",
                target_region=f"image-{index}",
                metrics={"invisible_text_region": f"text-{index}"},
                description="文本改为图片显示。",
            )
            for index in range(3)
        ]
        issues.append(
            Issue(
                id="blank-added",
                page=1,
                type=IssueType.ADDED_ELEMENT,
                severity=Severity.LOW,
                target_region="blank",
                metrics={"target_text": " \u200b\ufeff\u00ad "},
                description="新增区域。",
            )
        )
        page = PageQAResult(
            page=1,
            score=80,
            status=QAStatus.REVIEW,
            issues=issues,
        )

        self.assertEqual(count_problem_groups([page]), 1)


if __name__ == "__main__":
    unittest.main()
