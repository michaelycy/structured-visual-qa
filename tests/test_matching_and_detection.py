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
                    content=Content(text=" \u00a0 "),
                )
            ],
        )

        issues = RuleDetector().detect(
            source,
            target,
            RegionMatcher().match_page(source, target),
        )

        self.assertNotIn(IssueType.ADDED_ELEMENT, {issue.type for issue in issues})

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


if __name__ == "__main__":
    unittest.main()
