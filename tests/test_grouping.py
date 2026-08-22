import unittest

from document_qa.grouping import RegionGrouper
from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    ElementType,
    Page,
    TextStyle,
)


class RegionGrouperTests(unittest.TestCase):
    """验证 Block 分组、外接矩形和邻接关系。"""

    def test_groups_spans_from_same_source_block(self) -> None:
        """同一个 PDF 原始 Block 中的 Span 应组成一个 Region。"""

        blocks = [
            Block(
                id="span-1",
                page=1,
                type=ElementType.TEXT,
                bbox=BoundingBox(x=10, y=10, width=80, height=10),
                style=TextStyle(font_size=12),
                content=Content(text="第一行"),
                metadata={"source_block_index": 0},
            ),
            Block(
                id="span-2",
                page=1,
                type=ElementType.TEXT,
                bbox=BoundingBox(x=10, y=25, width=100, height=10),
                style=TextStyle(font_size=12),
                content=Content(text="第二行"),
                metadata={"source_block_index": 0},
            ),
        ]
        page = Page(
            document_id="doc",
            page=1,
            width=200,
            height=200,
            blocks=blocks,
        )

        grouped = RegionGrouper().group_page(page)

        self.assertEqual(len(grouped.regions), 1)
        self.assertEqual(grouped.regions[0].children, ["span-1", "span-2"])
        self.assertEqual(grouped.regions[0].bbox.height, 25)

    def test_attaches_vertical_neighbors(self) -> None:
        """按阅读顺序排列的 Region 应记录直接上下邻居。"""

        blocks = [
            Block(
                id=f"span-{index}",
                page=1,
                type=ElementType.TEXT,
                bbox=BoundingBox(x=10, y=10 + index * 30, width=80, height=10),
                content=Content(text=str(index)),
                metadata={"source_block_index": index},
            )
            for index in range(2)
        ]
        page = Page(
            document_id="doc",
            page=1,
            width=200,
            height=200,
            blocks=blocks,
        )

        regions = RegionGrouper().group_page(page).regions

        self.assertEqual(regions[0].relationships.below, regions[1].id)
        self.assertEqual(regions[1].relationships.above, regions[0].id)

    def test_splits_distant_labels_from_same_source_block(self) -> None:
        """同一原始 Block 中相距很远的同排标签不得合并成超宽 Region。"""

        blocks = [
            Block(
                id="label-left",
                page=1,
                type=ElementType.TEXT,
                bbox=BoundingBox(x=10, y=10, width=30, height=10),
                style=TextStyle(font_size=10),
                content=Content(text="左侧标签"),
                metadata={"source_block_index": 0},
            ),
            Block(
                id="label-right",
                page=1,
                type=ElementType.TEXT,
                bbox=BoundingBox(x=150, y=10, width=30, height=10),
                style=TextStyle(font_size=10),
                content=Content(text="右侧标签"),
                metadata={"source_block_index": 0},
            ),
        ]
        page = Page(
            document_id="doc",
            page=1,
            width=200,
            height=200,
            blocks=blocks,
        )

        regions = RegionGrouper().group_page(page).regions

        self.assertEqual([region.id for region in regions], ["p1-r0", "p1-r0-c2"])
        self.assertEqual([region.content.text for region in regions], ["左侧标签", "右侧标签"])


if __name__ == "__main__":
    unittest.main()
