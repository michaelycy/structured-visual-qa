"""基于 examples/ 真实中英文 PDF 的端到端回归测试。

这些断言锁定内置规则配置在真实双语样本上的表现（Golden Sample）。
调整 Profile 阈值或匹配算法时，此测试失败意味着校准结果发生了变化，
必须先确认变化合理（参见 docs/rule-calibration.md）再更新基线。
"""

import unittest
from pathlib import Path

from document_qa.pipeline import DocumentQAPipeline

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples"
SOURCE_PDF = EXAMPLE_DIR / "un-china-2024-en.pdf"
TARGET_PDF = EXAMPLE_DIR / "un-china-2024-zh.pdf"

# 内置 translation-balanced v1 在 2024-08 校准的基线。
BASELINE_SCORE = 91.804
BASELINE_PAGES = 46
SCORE_TOLERANCE = 0.5


@unittest.skipUnless(
    SOURCE_PDF.is_file() and TARGET_PDF.is_file(),
    "examples/ 中的真实样例 PDF 不存在",
)
class GoldenSampleRegressionTests(unittest.TestCase):
    """验证真实双语样本的端到端结果保持可复现。"""

    @classmethod
    def setUpClass(cls) -> None:
        """整个类只跑一次完整比较，控制用例耗时。"""

        cls.report = DocumentQAPipeline().compare(SOURCE_PDF, TARGET_PDF)

    def test_document_status_and_score_are_stable(self) -> None:
        """文档状态和总分必须停留在基线附近。"""

        self.assertEqual(self.report.status.value, "review")
        self.assertAlmostEqual(
            self.report.document_score, BASELINE_SCORE, delta=SCORE_TOLERANCE
        )

    def test_page_count_and_critical_issues(self) -> None:
        """页数不变，且真实翻译对不允许出现 Critical 问题。"""

        self.assertEqual(self.report.summary.pages, BASELINE_PAGES)
        self.assertEqual(self.report.summary.issue_counts["critical"], 0)

    def test_profile_snapshot_is_embedded(self) -> None:
        """报告必须内嵌 Profile 引用与快照，保证旧任务可复现。"""

        self.assertEqual(
            self.report.rule_profile_reference, "translation-balanced@1"
        )
        self.assertEqual(
            self.report.rule_profile_snapshot.profile_id, "translation-balanced"
        )


if __name__ == "__main__":
    unittest.main()
