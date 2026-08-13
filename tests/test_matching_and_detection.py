import unittest

from document_qa.detectors import RuleDetector
from document_qa.matching import RegionMatcher
from document_qa.schemas import (
    BoundingBox,
    Content,
    ElementType,
    IssueType,
    Page,
    QAStatus,
    Region,
    TextStyle,
)
from document_qa.scoring import QAScorer


def make_page(
    document_id: str,
    *,
    x_shift: float = 0,
    font_size: float = 12,
) -> Page:
    """构造包含文字和图片的最小页面，用于隔离测试匹配规则。"""

    return Page(
        document_id=document_id,
        page=1,
        width=200,
        height=200,
        regions=[
            Region(
                id=f"{document_id}-text",
                page=1,
                type=ElementType.PARAGRAPH,
                bbox=BoundingBox(x=10 + x_shift, y=10, width=100, height=20),
                style=TextStyle(font_size=font_size),
                content=Content(text="内容"),
            ),
            Region(
                id=f"{document_id}-image",
                page=1,
                type=ElementType.IMAGE,
                bbox=BoundingBox(x=10 + x_shift, y=80, width=80, height=60),
            ),
        ],
    )


class MatchingAndDetectionTests(unittest.TestCase):
    """验证全局匹配、差异计算、检测和评分的组合行为。"""

    def test_matches_regions_by_type_and_geometry(self) -> None:
        """轻微位移不能破坏文字和图片的一对一对应。"""

        result = RegionMatcher().match_page(
            make_page("source"), make_page("target", x_shift=2)
        )

        self.assertEqual(len(result.matches), 2)
        self.assertEqual(result.unmatched_source_region_ids, [])
        self.assertTrue(all(match.score > 0.9 for match in result.matches))

    def test_detects_shift_and_font_shrink(self) -> None:
        """显著横移和字号缩小必须生成可量化 Issue。"""

        source = make_page("source")
        target = make_page("target", x_shift=35, font_size=7)
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)
        issue_types = {issue.type for issue in issues}

        self.assertIn(IssueType.REGION_SHIFTED, issue_types)
        self.assertIn(IssueType.FONT_SHRINK, issue_types)
        _, status = QAScorer().score(issues)
        self.assertIn(status, {QAStatus.REVIEW, QAStatus.FAIL})

    def test_detects_missing_image_as_critical(self) -> None:
        """源图片未匹配时应产生 Critical 并直接导致 FAIL。"""

        source = make_page("source")
        target = make_page("target").model_copy(
            update={"regions": make_page("target").regions[:1]}
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)
        image_issues = [issue for issue in issues if issue.type == IssueType.MISSING_IMAGE]

        self.assertEqual(len(image_issues), 1)
        self.assertEqual(QAScorer().score(issues)[1], QAStatus.FAIL)


if __name__ == "__main__":
    unittest.main()

