import unittest

from document_qa.detectors import RuleDetector
from document_qa.matching import RegionMatcher
from document_qa.script_detection import text_advance_units
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


def make_vertical_text_region(
    document_id: str,
    region_id: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    font_size: float,
) -> Region:
    """构造窄高形（竖排/旋转 90°）的单行文本 Region。"""

    return Region(
        id=region_id,
        page=1,
        type=ElementType.PARAGRAPH,
        bbox=BoundingBox(x=x, y=y, width=width, height=height),
        style=TextStyle(font_size=font_size),
        content=Content(text=text),
    )


def make_single_region_page(document_id: str, region: Region) -> Page:
    """构造只含一个 Region 的页面，用于 1↔1 匹配的几何检测。"""

    return Page(
        document_id=document_id,
        page=1,
        width=612,
        height=792,
        regions=[region],
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

    def test_ignores_vertical_label_height_change(self) -> None:
        """竖排短标签高度随译文字符密度伸缩时不应判为尺寸剧变。

        复现真实记录 20260901-065834 的 p2 轴标签场景：竖排
        "Total Number of Deals"（21 字符 ≈ 11em）译为"交易总数"
        （4 全角 ≈ 4em），高度 -63% 与密度预期一致，属于正常适配。
        """

        source = make_single_region_page(
            "source",
            make_vertical_text_region(
                "source",
                "source-r1",
                x=560,
                y=432,
                width=10.5,
                height=86,
                text="Total Number of Deals",
                font_size=8,
            ),
        )
        target = make_single_region_page(
            "target",
            make_vertical_text_region(
                "target",
                "target-r1",
                x=556,
                y=459,
                width=11.5,
                height=32,
                text="交易总数",
                font_size=8,
            ),
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertNotIn(IssueType.REGION_RESIZED, {issue.type for issue in issues})

    def test_reports_vertical_label_density_inconsistent_height_change(self) -> None:
        """竖排标签高度变化偏离密度预期时仍应判为尺寸剧变。

        字符被逐字堆叠（行距拉爆）时高度变化无法用译文字数解释，
        该破坏必须继续由 resize 规则捕获，豁免不得吞掉。
        """

        source = make_single_region_page(
            "source",
            make_vertical_text_region(
                "source",
                "source-r1",
                x=560,
                y=432,
                width=10,
                height=40,
                text="Vaccines",
                font_size=8,
            ),
        )
        target = make_single_region_page(
            "target",
            make_vertical_text_region(
                "target",
                "target-r1",
                x=560,
                y=432,
                width=10,
                height=90,
                text="Vaccines",
                font_size=8,
            ),
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertIn(IssueType.REGION_RESIZED, {issue.type for issue in issues})

    def test_reports_vertical_label_with_font_shrink(self) -> None:
        """竖排标签伴随字号缩小时不得豁免，仍应报告尺寸/字号问题。

        复现真实记录中 "Hepatic"→"肝脏" 的场景：目标字号 8pt→5pt，
        高度收缩主要由字号缩小贡献，超出字号稳定门控，不在豁免范围。
        """

        source = make_single_region_page(
            "source",
            make_vertical_text_region(
                "source",
                "source-r1",
                x=560,
                y=432,
                width=10,
                height=40,
                text="Hepatic",
                font_size=8,
            ),
        )
        target = make_single_region_page(
            "target",
            make_vertical_text_region(
                "target",
                "target-r1",
                x=560,
                y=452,
                width=10,
                height=17,
                text="肝脏",
                font_size=5,
            ),
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)
        issue_types = {issue.type for issue in issues}

        self.assertIn(IssueType.REGION_RESIZED, issue_types)


class TextAdvanceUnitsTests(unittest.TestCase):
    """验证跨语言字符 advance 估算，保证密度归一口径稳定。"""

    def test_fullwidth_chars_count_as_one_em(self) -> None:
        """CJK/全角字符按 1em 计，含兼容表意文字区。"""

        self.assertAlmostEqual(text_advance_units("交易总数"), 4.0)
        # U+F9EA 属 CJK 兼容表意文字，翻译 PDF 常见，必须按全角计。
        self.assertAlmostEqual(text_advance_units("交易总数"), 4.0)
        self.assertAlmostEqual(text_advance_units("ＡＢ"), 2.0)

    def test_halfwidth_chars_and_spaces_count_as_half_em(self) -> None:
        """拉丁/数字/半角标点与空格按 0.5em 计。"""

        self.assertAlmostEqual(text_advance_units("Total"), 2.5)
        self.assertAlmostEqual(text_advance_units("a b"), 1.5)
        self.assertAlmostEqual(text_advance_units("a, b"), 2.0)

    def test_control_characters_are_not_counted(self) -> None:
        """换行等控制字符不占墨迹，不计入 advance。"""

        self.assertAlmostEqual(text_advance_units("ab\ncd"), 2.0)
        self.assertAlmostEqual(text_advance_units(""), 0.0)


if __name__ == "__main__":
    unittest.main()
