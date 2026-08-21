import unittest

from document_qa.detectors import RuleDetector
from document_qa.matching import RegionMatcher
from document_qa.schemas import (
    BoundingBox,
    Content,
    ElementType,
    IssueType,
    Page,
    Region,
    TextStyle,
)


def make_text_page(
    document_id: str,
    *,
    lefts: list[float],
    widths: list[float],
    texts: list[str] | None = None,
) -> Page:
    """按给定行左边缘和宽度构造单段文本页面。"""

    resolved_texts = texts or [f"line-{index}" for index in range(len(lefts))]
    return Page(
        document_id=document_id,
        page=1,
        width=200,
        height=240,
        regions=[
            Region(
                id=f"{document_id}-line-{index}",
                page=1,
                type=ElementType.PARAGRAPH,
                bbox=BoundingBox(
                    x=left,
                    y=20 + index * 18,
                    width=widths[index],
                    height=16,
                ),
                style=TextStyle(font_size=12),
                content=Content(text=resolved_texts[index]),
            )
            for index, left in enumerate(lefts)
        ],
    )


class TextAlignmentDetectionTests(unittest.TestCase):
    """验证段落对齐变化、边界行为与几何误报抑制。"""

    def test_detects_right_to_left_alignment_once(self) -> None:
        """右对齐段落变左对齐时应生成一条 High，且不重复报行级偏移。"""

        source = make_text_page(
            "source",
            lefts=[80, 50, 100, 60],
            widths=[100, 130, 80, 120],
        )
        target = make_text_page(
            "target",
            lefts=[20, 20, 20],
            widths=[120, 90, 130],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)
        alignment_issues = [
            issue
            for issue in issues
            if issue.type == IssueType.TEXT_ALIGNMENT_CHANGED
        ]

        self.assertEqual(len(alignment_issues), 1)
        self.assertEqual(alignment_issues[0].metrics["source_alignment"], "right")
        self.assertEqual(alignment_issues[0].metrics["target_alignment"], "left")
        self.assertNotIn(IssueType.REGION_SHIFTED, {issue.type for issue in issues})

    def test_keeps_same_right_alignment_without_issue(self) -> None:
        """译文行长变化但双方仍右对齐时不得误报对齐变化。"""

        source = make_text_page(
            "source",
            lefts=[80, 50, 100],
            widths=[100, 130, 80],
        )
        target = make_text_page(
            "target",
            lefts=[60, 90, 40],
            widths=[120, 90, 140],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertNotIn(
            IssueType.TEXT_ALIGNMENT_CHANGED, {issue.type for issue in issues}
        )

    def test_ignores_short_label_width_change(self) -> None:
        """短标签翻译后文字变短且高度字号稳定时不应判为尺寸剧变。"""

        source = make_text_page(
            "source",
            lefts=[20],
            widths=[100],
            texts=["CAR STRUCTURE"],
        )
        target = make_text_page(
            "target",
            lefts=[20],
            widths=[40],
            texts=["CAR 结构"],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertNotIn(IssueType.REGION_RESIZED, {issue.type for issue in issues})

    def test_reports_long_text_width_change(self) -> None:
        """长文本 Region 的宽度剧变仍应保留原有尺寸检测能力。"""

        source = make_text_page(
            "source",
            lefts=[20],
            widths=[100],
            texts=["A long paragraph that must remain geometrically comparable"],
        )
        target = make_text_page(
            "target",
            lefts=[20],
            widths=[40],
            texts=["另一段足够长的目标文本用于验证区域宽度剧变仍会被检测出来"],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertIn(IssueType.REGION_RESIZED, {issue.type for issue in issues})


if __name__ == "__main__":
    unittest.main()
