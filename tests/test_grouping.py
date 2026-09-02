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

    def _toc_line_block(
        self, block_id: str, block_index: int, y: float, text: str
    ) -> Block:
        """构造目录行样式的文本 Block（同栏、同字号、行距 18）。"""

        return Block(
            id=block_id,
            page=2,
            type=ElementType.TEXT,
            bbox=BoundingBox(x=520, y=y, width=100, height=12),
            style=TextStyle(font_size=12),
            content=Content(text=text),
            metadata={"source_block_index": block_index, "source_line_index": block_index},
        )

    def test_merges_interleaved_component_from_other_source_block(self) -> None:
        """内容流错排嵌进其他 Block 行间的文本行应归并回同栏 Region。

        复现真实案例（历史记录 20260901-150635 第 2 页）：译文行被画进
        左栏原始 Block，按 Block 分组后其 BBox 被同栏多行 Region 的并集
        BBox 完全框住，继而产生虚假重叠与新增报告。
        """

        blocks = [
            self._toc_line_block("a-1", 8, 172, "第一行"),
            self._toc_line_block("a-2", 8, 190, "第二行"),
            self._toc_line_block("a-3", 8, 226, "第四行"),
            self._toc_line_block("a-4", 8, 244, "第五行"),
            # 译文行物理上位于第二行与第四行之间，却被画进另一个原始 Block。
            self._toc_line_block("b-1", 6, 208, "第三行"),
        ]
        page = Page(
            document_id="doc",
            page=2,
            width=960,
            height=540,
            blocks=blocks,
        )

        regions = RegionGrouper().group_page(page).regions

        self.assertEqual(len(regions), 1)
        merged = regions[0]
        self.assertEqual(merged.id, "p2-r8")
        self.assertEqual(merged.children, ["a-1", "a-2", "b-1", "a-3", "a-4"])
        self.assertEqual(merged.content.text.splitlines(), ["第一行", "第二行", "第三行", "第四行", "第五行"])
        self.assertEqual(merged.metadata["merged_source_block_indexes"], [6])

    def test_keeps_nested_component_with_colliding_children(self) -> None:
        """子行真实碰撞的嵌套分量不得归并，必须留给重叠检测上报。"""

        blocks = [
            self._toc_line_block("a-1", 8, 172, "正文行"),
            # 与正文行几乎完全重叠的独立 Block：真实文字重叠场景。
            self._toc_line_block("b-1", 6, 173, "重叠行"),
        ]
        page = Page(
            document_id="doc",
            page=2,
            width=960,
            height=540,
            blocks=blocks,
        )

        regions = RegionGrouper().group_page(page).regions

        self.assertEqual(len(regions), 2)

    def test_keeps_nested_component_with_incompatible_style(self) -> None:
        """样式不兼容（字号不同）的嵌套分量不得归并。"""

        blocks = [
            self._toc_line_block("a-1", 8, 172, "正文行一"),
            self._toc_line_block("a-2", 8, 210, "正文行二"),
            self._toc_line_block("b-1", 6, 190, "大字注记"),
        ]
        # 嵌套行使用显著更大的字号，模拟标题/水印类独立文本；几何上
        # 完整落在容器两行之间的空档内且不与任何子行碰撞。
        blocks[-1].style = TextStyle(font_size=20)
        page = Page(
            document_id="doc",
            page=2,
            width=960,
            height=540,
            blocks=blocks,
        )

        regions = RegionGrouper().group_page(page).regions

        self.assertEqual(len(regions), 2)


if __name__ == "__main__":
    unittest.main()
