import unittest

from document_qa.detectors import RuleDetector
from document_qa.matching import RegionMatcher
from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    ElementType,
    Issue,
    IssueType,
    Page,
    QAStatus,
    Region,
    Severity,
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

    def test_ignores_blank_unmatched_target_text(self) -> None:
        """PDF 导出器产生的空白文本框不应计为新增元素。"""

        source = Page(document_id="source", page=1, width=200, height=200)
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="target-blank",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=20, height=10),
                    content=Content(text=" \u00a0\u200b\ufeff\u00ad\u202e "),
                )
            ],
        )

        issues = RuleDetector().detect(
            source,
            target,
            RegionMatcher().match_page(source, target),
        )

        self.assertNotIn(IssueType.ADDED_ELEMENT, {issue.type for issue in issues})

    def test_ignores_control_only_invisible_text(self) -> None:
        """只有 Unicode 控制字符的透明文本框不应被判为隐形文字。"""

        bbox = BoundingBox(x=10, y=10, width=20, height=10)
        source = Page(document_id="source", page=1, width=200, height=200)
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=200,
            metadata={"background_color": "#FFFFFF"},
            blocks=[
                Block(
                    id="target-control-block",
                    page=1,
                    type=ElementType.TEXT,
                    bbox=bbox,
                    content=Content(text="\u200b\ufeff\u00ad"),
                    metadata={"opacity": 0.0},
                )
            ],
            regions=[
                Region(
                    id="target-control",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=bbox,
                    content=Content(text="\u200b\ufeff\u00ad"),
                    children=["target-control-block"],
                )
            ],
        )

        issues = RuleDetector().detect(
            source,
            target,
            RegionMatcher().match_page(source, target),
        )

        self.assertNotIn(IssueType.INVISIBLE_TEXT, {issue.type for issue in issues})

    def test_ignores_geometry_diff_between_text_and_image(self) -> None:
        """文字被全局分配到图片时不得产生无意义的几何问题。"""

        source = Page(
            document_id="source",
            page=1,
            width=960,
            height=540,
            regions=[
                Region(
                    id="source-heading",
                    page=1,
                    type=ElementType.HEADING,
                    bbox=BoundingBox(x=608, y=242, width=201, height=16),
                    content=Content(text="标题"),
                )
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=960,
            height=540,
            regions=[
                Region(
                    id="target-image",
                    page=1,
                    type=ElementType.IMAGE,
                    bbox=BoundingBox(x=893, y=5, width=47, height=46),
                )
            ],
        )

        result = RegionMatcher().match_page(source, target)
        issues = RuleDetector().detect(source, target, result)

        issue_types = {issue.type for issue in issues}
        self.assertNotIn(IssueType.REGION_SHIFTED, issue_types)
        self.assertNotIn(IssueType.REGION_RESIZED, issue_types)

    def test_detects_text_rasterized_without_duplicate_added_image(self) -> None:
        """透明译文层与同位置图片应合并为一个文字栅格化问题。"""

        bbox = BoundingBox(x=20, y=30, width=100, height=20)
        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="source-text",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=bbox,
                    content=Content(text="원문"),
                )
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=200,
            blocks=[
                Block(
                    id="target-text-block",
                    page=1,
                    type=ElementType.TEXT,
                    bbox=bbox,
                    content=Content(text="译文"),
                    metadata={"opacity": 0.0},
                ),
                Block(
                    id="target-image-block",
                    page=1,
                    type=ElementType.IMAGE,
                    bbox=bbox,
                ),
            ],
            regions=[
                Region(
                    id="target-text",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=bbox,
                    content=Content(text="译文"),
                    children=["target-text-block"],
                ),
                Region(
                    id="target-image",
                    page=1,
                    type=ElementType.IMAGE,
                    bbox=bbox,
                    children=["target-image-block"],
                ),
            ],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertEqual(
            [issue.type for issue in issues].count(IssueType.TEXT_RASTERIZED), 1
        )
        self.assertNotIn(IssueType.ADDED_ELEMENT, {issue.type for issue in issues})
        self.assertNotIn(IssueType.INVISIBLE_TEXT, {issue.type for issue in issues})
        rasterized = next(
            issue for issue in issues if issue.type == IssueType.TEXT_RASTERIZED
        )
        self.assertEqual(rasterized.metrics["type_change"], "text->image")
        self.assertEqual(rasterized.target_region, "target-image")

    def test_visible_text_over_image_is_not_text_rasterized(self) -> None:
        """正常可见文字叠在图片上时不得误判为文字栅格化。"""

        bbox = BoundingBox(x=20, y=30, width=100, height=20)
        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="source-text",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=bbox,
                    content=Content(text="source"),
                )
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=200,
            blocks=[
                Block(
                    id="target-text-block",
                    page=1,
                    type=ElementType.TEXT,
                    bbox=bbox,
                    content=Content(text="target"),
                    metadata={"opacity": 1.0},
                )
            ],
            regions=[
                Region(
                    id="target-text",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=bbox,
                    content=Content(text="target"),
                    children=["target-text-block"],
                ),
                Region(
                    id="target-image",
                    page=1,
                    type=ElementType.IMAGE,
                    bbox=bbox,
                ),
            ],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertNotIn(IssueType.TEXT_RASTERIZED, {issue.type for issue in issues})
        self.assertIn(IssueType.ADDED_ELEMENT, {issue.type for issue in issues})

    def test_ignores_source_text_merged_into_target_text_box(self) -> None:
        """目标文本框覆盖多个源段落时，不应把额外源段落判为缺失。"""

        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="source-a",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=100, height=20),
                ),
                Region(
                    id="source-b",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=35, width=100, height=20),
                ),
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="target-merged",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=100, height=50),
                )
            ],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertNotIn(IssueType.MISSING_ELEMENT, {issue.type for issue in issues})

    def test_ignores_preexisting_text_image_overlap(self) -> None:
        """源目标都存在的背景图叠字属于设计关系，不应报告异常。"""

        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="source-image",
                    page=1,
                    type=ElementType.IMAGE,
                    bbox=BoundingBox(x=0, y=0, width=200, height=200),
                ),
                Region(
                    id="source-text",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=20, y=20, width=100, height=30),
                ),
            ],
        )
        target = source.model_copy(
            update={
                "document_id": "target",
                "regions": [
                    source.regions[0].model_copy(update={"id": "target-image"}),
                    source.regions[1].model_copy(update={"id": "target-text"}),
                ],
            }
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertNotIn(
            IssueType.TEXT_IMAGE_OVERLAP, {issue.type for issue in issues}
        )

    def test_detects_new_text_image_overlap(self) -> None:
        """目标文本移动到图片上时，新增拓扑重叠必须报告。"""

        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="source-image",
                    page=1,
                    type=ElementType.IMAGE,
                    bbox=BoundingBox(x=0, y=100, width=200, height=100),
                ),
                Region(
                    id="source-text",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=20, y=20, width=100, height=30),
                ),
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="target-image",
                    page=1,
                    type=ElementType.IMAGE,
                    bbox=BoundingBox(x=0, y=100, width=200, height=100),
                ),
                Region(
                    id="target-text",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=20, y=110, width=100, height=30),
                ),
            ],
        )
        result = RegionMatcher().match_page(source, target)

        issues = RuleDetector().detect(source, target, result)

        self.assertIn(IssueType.TEXT_IMAGE_OVERLAP, {issue.type for issue in issues})

    def test_repeated_issue_type_has_page_deduction_cap(self) -> None:
        """重复图表标签问题应全部保留，但不能无限重复扣减页面分数。"""

        issues = [
            Issue(
                id=f"font-{index}",
                page=1,
                type=IssueType.FONT_SHRINK,
                severity=Severity.HIGH,
                description="图表标签字号缩小。",
            )
            for index in range(12)
        ]

        score, status = QAScorer().score(issues)

        self.assertEqual(score, 90.0)
        self.assertEqual(status, QAStatus.REVIEW)


class FragmentationDetectionTests(unittest.TestCase):
    """验证碎片检测对拉丁缩写碎片与 CJK 完整短词的区分。

    回归背景：真实记录 20260901-063516 第 1 页，图表图例"法务/
    欧洲/日本"等两字横排完整词被误报为碎片——CJK 字符 isalpha
    为 True，"字母数 ≤ 3"判据天然命中中文短词。
    """

    @staticmethod
    def detect_for(source_text: str, target_regions: list[Region]):
        """构造同页源/目标并返回碎片 Issue 列表。"""

        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=400,
            regions=[
                Region(
                    id="source-label",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=100, height=20),
                    content=Content(text=source_text),
                )
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=400,
            regions=target_regions,
        )
        result = RegionMatcher().match_page(source, target)
        issues = RuleDetector().detect(source, target, result)
        return [i for i in issues if i.type == IssueType.TEXT_FRAGMENTED]

    def test_latin_letter_stack_is_flagged(self) -> None:
        """拉丁缩写被逐字母竖排（P\\nK）必须报告。"""

        issues = self.detect_for(
            "PK",
            [
                Region(
                    id="target-frag",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=12, height=26),
                    content=Content(text="P\nK"),
                )
            ],
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].metrics["source_text"], "PK")

    def test_cjk_horizontal_word_is_not_flagged(self) -> None:
        """横排单行的两字中文词（图例"法务"）是完整词，不得报告。"""

        issues = self.detect_for(
            "Legal",
            [
                Region(
                    id="target-cjk",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=16, height=11.6),
                    content=Content(text="法务"),
                )
            ],
        )
        self.assertEqual(issues, [])

    def test_cjk_vertical_stack_is_flagged(self) -> None:
        """CJK 文本带换行竖排（"法\\n务"）仍是碎片，必须报告。"""

        issues = self.detect_for(
            "Legal",
            [
                Region(
                    id="target-cjk-vert",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=12, height=26),
                    content=Content(text="法\n务"),
                )
            ],
        )
        self.assertEqual(len(issues), 1)

    def test_single_cjk_char_region_still_flagged(self) -> None:
        """单字 CJK 窄 Region（逐字拆散证据）保持报告，不被豁免。"""

        issues = self.detect_for(
            "Legal",
            [
                Region(
                    id="target-cjk-char",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=12, height=11.6),
                    content=Content(text="法"),
                )
            ],
        )
        self.assertEqual(len(issues), 1)

    def test_kept_abbreviation_exempt_by_source_page_tokens(self) -> None:
        """译文保留的缩写/品牌名（NDA、A轮的 A）按源页词形豁免。

        回归背景：真实记录 20260901-063516 后续复核，图例 M→1 配对
        错位（"A轮"配到"Seed"），豁免必须取源页面级词形证据。
        """

        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=400,
            regions=[
                Region(
                    id="source-seed",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=60, height=14),
                    content=Content(text="Seed"),
                ),
                Region(
                    id="source-series-a",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=200, width=80, height=14),
                    content=Content(text="Series A"),
                ),
                Region(
                    id="source-nda",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=300, width=50, height=14),
                    content=Content(text="NDA"),
                ),
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=400,
            regions=[
                Region(
                    id="target-round-a",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=16, height=11.6),
                    content=Content(text="A轮"),
                ),
                Region(
                    id="target-nda",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=40, width=18, height=11.6),
                    content=Content(text="NDA"),
                ),
            ],
        )
        result = RegionMatcher().match_page(source, target)
        issues = [
            i
            for i in RuleDetector().detect(source, target, result)
            if i.type == IssueType.TEXT_FRAGMENTED
        ]
        self.assertEqual(issues, [])

    def test_fragment_piece_without_source_word_still_flagged(self) -> None:
        """片断（"SAE"拆出的"SA"）不是源页完整词，仍按碎片报告。"""

        issues = self.detect_for(
            "SAE",
            [
                Region(
                    id="target-piece",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=16, height=11.6),
                    content=Content(text="SA"),
                )
            ],
        )
        self.assertEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
