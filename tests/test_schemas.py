import unittest

from pydantic import ValidationError

from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    ElementType,
    Issue,
    IssueType,
    Page,
    Region,
    Severity,
    TextStyle,
)


def make_block(block_id: str = "block-1", page: int = 1) -> Block:
    """构造可复用的最小文本 Block。"""

    return Block(
        id=block_id,
        page=page,
        type=ElementType.TEXT,
        bbox=BoundingBox(x=72, y=140, width=440, height=25),
        style=TextStyle(font_family="Arial", font_size=11),
        content=Content(text="Our platform", language="en"),
    )


class SchemaTests(unittest.TestCase):
    """验证核心 Schema 的嵌套、约束和序列化行为。"""

    def test_page_accepts_nested_blocks_and_regions(self) -> None:
        """合法的 Block 和 Region 应被页面接受并稳定序列化。"""

        block = make_block()
        region = Region(
            id="region-1",
            page=1,
            type=ElementType.PARAGRAPH,
            bbox=BoundingBox(x=72, y=140, width=440, height=85),
            children=[block.id],
        )

        page = Page(
            document_id="source-document",
            page=1,
            width=595,
            height=842,
            blocks=[block],
            regions=[region],
        )

        self.assertEqual(page.regions[0].children, ["block-1"])
        self.assertEqual(page.model_dump(mode="json")["blocks"][0]["type"], "text")

    def test_page_rejects_unknown_region_block_reference(self) -> None:
        """Region 不得引用当前页不存在的 Block。"""

        with self.assertRaisesRegex(ValidationError, "unknown blocks"):
            Page(
                document_id="source-document",
                page=1,
                width=595,
                height=842,
                regions=[
                    Region(
                        id="region-1",
                        page=1,
                        type=ElementType.PARAGRAPH,
                        bbox=BoundingBox(x=72, y=140, width=440, height=85),
                        children=["missing-block"],
                    )
                ],
            )

    def test_page_rejects_child_from_another_page(self) -> None:
        """页面不得包含属于其他页的子对象。"""

        with self.assertRaisesRegex(ValidationError, "belong to this page"):
            Page(
                document_id="source-document",
                page=1,
                width=595,
                height=842,
                blocks=[make_block(page=2)],
            )

    def test_bbox_allows_out_of_page_coordinates_but_not_invalid_size(self) -> None:
        """允许检测所需的越界坐标，但拒绝零面积矩形。"""

        bbox = BoundingBox(x=-2, y=830, width=100, height=30)
        self.assertEqual(bbox.bottom, 860)

        with self.assertRaises(ValidationError):
            BoundingBox(x=0, y=0, width=0, height=20)

    def test_issue_serializes_as_unified_detector_output(self) -> None:
        """Issue 应保持枚举值和检测指标的 JSON 表达。"""

        issue = Issue(
            id="issue-001",
            page=3,
            type=IssueType.TEXT_IMAGE_OVERLAP,
            severity=Severity.CRITICAL,
            source_region="source-region-3",
            target_region="target-region-4",
            bbox=BoundingBox(x=100, y=230, width=400, height=40),
            metrics={"overlap_ratio": 0.18},
            description="Translated paragraph overlaps the image below.",
            detector="overlap-detector",
        )

        payload = issue.model_dump(mode="json")
        self.assertEqual(payload["severity"], "critical")
        self.assertEqual(payload["metrics"]["overlap_ratio"], 0.18)

    def test_models_forbid_unknown_fields(self) -> None:
        """严格模型必须拒绝未声明字段。"""

        with self.assertRaisesRegex(ValidationError, "Extra inputs are not permitted"):
            Block(**make_block().model_dump(), unexpected=True)


if __name__ == "__main__":
    unittest.main()
