"""使用确定性规则把解析 Block 组合为语义 Region。"""

from collections import defaultdict
from statistics import median

from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    ElementType,
    Page,
    Region,
    RegionRelationships,
)


class RegionGrouper:
    """按原始 PDF Block 分组，并补充基础类型和邻接关系。"""

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """允许注入版本化分组配置（标题判定阈值）；缺省使用内置 Profile。"""

        self.profile = profile or default_rule_profile()

    def group_page(self, page: Page) -> Page:
        """为页面生成 Region，并返回新的不可变语义快照。"""

        groups: dict[int, list[Block]] = defaultdict(list)
        for fallback_index, block in enumerate(page.blocks):
            source_index = block.metadata.get("source_block_index", fallback_index)
            groups[int(source_index)].append(block)

        text_sizes = [
            block.style.font_size
            for block in page.blocks
            if block.type == ElementType.TEXT
            and block.style is not None
            and block.style.font_size is not None
        ]
        median_font_size = median(text_sizes) if text_sizes else None

        regions = [
            self._build_region(page.page, source_index, blocks, median_font_size)
            for source_index, blocks in sorted(groups.items())
        ]
        regions.sort(key=lambda region: (region.bbox.y, region.bbox.x))
        regions = self._attach_relationships(regions)
        return page.model_copy(update={"regions": regions})

    def _build_region(
        self,
        page_number: int,
        source_index: int,
        blocks: list[Block],
        median_font_size: float | None,
    ) -> Region:
        """合并同一原始 Block 的几何范围、文本和代表样式。"""

        bbox = self._union_bbox(blocks)
        first_block = blocks[0]
        text_blocks = [block for block in blocks if block.type == ElementType.TEXT]

        if first_block.type == ElementType.IMAGE:
            region_type = ElementType.IMAGE
            content = first_block.content
            style = None
        elif not text_blocks:
            # 非 TEXT 非 IMAGE 的 Block（TABLE/CHART/SHAPE）单独成组时
            # 没有可比文本；按首块类型建 Region，内容与样式透传。
            region_type = first_block.type
            content = first_block.content
            style = first_block.style
        else:
            representative = max(
                text_blocks,
                key=lambda block: block.style.font_size
                if block.style and block.style.font_size
                else 0,
            )
            largest_size = (
                representative.style.font_size if representative.style else None
            )
            # 相对正文显著放大的文本先标记为标题，后续可替换为训练模型。
            is_heading = bool(
                median_font_size
                and largest_size
                and largest_size >= median_font_size * self.profile.grouping.heading_ratio
            )
            region_type = ElementType.HEADING if is_heading else ElementType.PARAGRAPH
            content = Content(
                text="\n".join(
                    block.content.text
                    for block in text_blocks
                    if block.content and block.content.text
                )
            )
            style = representative.style

        return Region(
            id=f"p{page_number}-r{source_index}",
            page=page_number,
            type=region_type,
            bbox=bbox,
            style=style,
            content=content,
            children=[block.id for block in blocks],
            metadata={"source_block_index": source_index},
        )

    @staticmethod
    def _union_bbox(blocks: list[Block]) -> BoundingBox:
        """计算一组 Block 的最小外接矩形。"""

        x0 = min(block.bbox.x for block in blocks)
        y0 = min(block.bbox.y for block in blocks)
        x1 = max(block.bbox.right for block in blocks)
        y1 = max(block.bbox.bottom for block in blocks)
        return BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)

    @staticmethod
    def _attach_relationships(regions: list[Region]) -> list[Region]:
        """按照阅读顺序写入直接上下邻居，作为后续匹配扩展信号。"""

        updated: list[Region] = []
        for index, region in enumerate(regions):
            relationships = RegionRelationships(
                above=regions[index - 1].id if index > 0 else None,
                below=regions[index + 1].id if index + 1 < len(regions) else None,
            )
            updated.append(region.model_copy(update={"relationships": relationships}))
        return updated

