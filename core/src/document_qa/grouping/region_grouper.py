"""使用确定性规则把解析 Block 组合为语义 Region。"""

from collections import defaultdict
import re
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

    _TEXT_ITEM_PREFIX = re.compile(
        r"^\s*(?:[•·◦▪▫‣⁃○●□■※〮]|[:：]|\(?\d{1,3}\)?[.)、．])"
    )

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

        regions = []
        for source_index, blocks in sorted(groups.items()):
            components = self._split_disconnected_blocks(blocks)
            for component_index, component in enumerate(components):
                region_id = f"p{page.page}-r{source_index}"
                if component_index:
                    region_id = f"{region_id}-c{component_index + 1}"
                regions.append(
                    self._build_region(
                        page.page,
                        source_index,
                        component,
                        median_font_size,
                        region_id,
                        component_index,
                        len(components),
                    )
                )
        regions.sort(key=lambda region: (region.bbox.y, region.bbox.x))
        regions = self._attach_relationships(regions)
        return page.model_copy(update={"regions": regions})

    def _build_region(
        self,
        page_number: int,
        source_index: int,
        blocks: list[Block],
        median_font_size: float | None,
        region_id: str,
        component_index: int,
        component_count: int,
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
            id=region_id,
            page=page_number,
            type=region_type,
            bbox=bbox,
            style=style,
            content=content,
            children=[block.id for block in blocks],
            metadata={
                "source_block_index": source_index,
                "source_component_index": component_index,
                "_source_block_component_count": component_count,
            },
        )

    def _split_disconnected_blocks(self, blocks: list[Block]) -> list[list[Block]]:
        """拆开原始 Block 中空间上明显不连通的独立文本标签。

        PyMuPDF 偶尔把流程图同一行的多个标签放进一个原始 Block。仅按
        source_block_index 合并会产生横跨多个节点的 Region，继而污染匹配与
        几何检测。这里按视觉连通分量拆分；正常段落行因水平重叠或左边缘接近
        仍保持在同一 Region。
        """

        if len(blocks) < 2 or any(block.type != ElementType.TEXT for block in blocks):
            return [blocks]

        ordered_blocks = sorted(
            blocks, key=lambda block: (block.bbox.y, block.bbox.x, block.id)
        )
        components: list[list[Block]] = []
        for run in self._split_cross_line_runs(ordered_blocks):
            components.extend(self._connected_components(run))
        components.sort(
            key=lambda component: (
                min(block.bbox.y for block in component),
                min(block.bbox.x for block in component),
            )
        )
        return components

    def _split_cross_line_runs(self, blocks: list[Block]) -> list[list[Block]]:
        """先按跨行样式和条目边界切段，禁止连通图绕过边界回连。"""

        lines: list[list[Block]] = []
        for block in blocks:
            line_index = block.metadata.get("source_line_index")
            if (
                lines
                and line_index is not None
                and line_index
                == lines[-1][0].metadata.get("source_line_index")
            ):
                lines[-1].append(block)
            else:
                lines.append([block])

        runs: list[list[Block]] = []
        for line in lines:
            if not runs:
                runs.append(list(line))
                continue
            previous_line = self._last_visual_line(runs[-1])
            previous_style_block = max(
                previous_line, key=lambda block: (block.bbox.width, block.id)
            )
            current_style_block = max(
                line, key=lambda block: (block.bbox.width, block.id)
            )
            if not self._styles_are_compatible(
                previous_style_block, current_style_block
            ) or self._line_starts_new_text_item(line):
                runs.append(list(line))
            else:
                runs[-1].extend(line)
        return runs

    @staticmethod
    def _last_visual_line(blocks: list[Block]) -> list[Block]:
        """返回分段中的最后一个视觉行，供下一行做样式比较。"""

        line_index = blocks[-1].metadata.get("source_line_index")
        if line_index is None:
            return [blocks[-1]]
        return [
            block
            for block in blocks
            if block.metadata.get("source_line_index") == line_index
        ]

    def _line_starts_new_text_item(self, blocks: list[Block]) -> bool:
        """按行内阅读顺序识别编号、项目符号或冒号明细。"""

        text = "".join(
            block.content.text
            for block in sorted(blocks, key=lambda block: (block.bbox.x, block.id))
            if block.content and block.content.text
        )
        return bool(self._TEXT_ITEM_PREFIX.match(text))

    def _connected_components(self, blocks: list[Block]) -> list[list[Block]]:
        """在不含硬样式边界的分段内部计算空间连通分量。"""

        remaining = set(range(len(blocks)))
        components: list[list[Block]] = []
        while remaining:
            seed = min(remaining)
            remaining.remove(seed)
            component_indexes = [seed]
            queue = [seed]
            while queue:
                current = queue.pop()
                connected = [
                    candidate
                    for candidate in sorted(remaining)
                    if self._blocks_are_connected(blocks[current], blocks[candidate])
                ]
                for candidate in connected:
                    remaining.remove(candidate)
                    component_indexes.append(candidate)
                    queue.append(candidate)
            component = [blocks[index] for index in component_indexes]
            component.sort(key=lambda block: (block.bbox.y, block.bbox.x, block.id))
            components.append(component)

        return components

    def _blocks_are_connected(self, first: Block, second: Block) -> bool:
        """按行高归一化间距判断两个文本 Span 是否属于同一视觉文本块。"""

        first, second = sorted(
            (first, second), key=lambda block: (block.bbox.y, block.bbox.x, block.id)
        )
        if not self._same_source_line(first, second):
            # 行内强调色、加粗词等仍可属于同一 Region；跨行则必须保持
            # 颜色、字号、字重和斜体兼容，避免标题吞并后续正文。
            if not self._styles_are_compatible(first, second):
                return False
            if self._starts_new_text_item(second):
                return False

        gap_limit = (
            max(first.bbox.height, second.bbox.height)
            * self.profile.grouping.disconnected_span_gap_ratio
        )
        horizontal_gap = max(
            0.0,
            max(first.bbox.x, second.bbox.x)
            - min(first.bbox.right, second.bbox.right),
        )
        vertical_gap = max(
            0.0,
            max(first.bbox.y, second.bbox.y)
            - min(first.bbox.bottom, second.bbox.bottom),
        )
        horizontal_overlap = horizontal_gap == 0
        vertical_overlap = vertical_gap == 0
        same_left_edge = abs(first.bbox.x - second.bbox.x) <= gap_limit
        return (
            vertical_overlap and horizontal_gap <= gap_limit
        ) or (
            vertical_gap <= gap_limit and (horizontal_overlap or same_left_edge)
        )

    @staticmethod
    def _same_source_line(first: Block, second: Block) -> bool:
        """判断两个 Span 是否来自同一 PDF 视觉行。"""

        first_line = first.metadata.get("source_line_index")
        second_line = second.metadata.get("source_line_index")
        return first_line is not None and first_line == second_line

    def _styles_are_compatible(self, first: Block, second: Block) -> bool:
        """判断跨行文字样式是否足够一致，可以继续组成同一 Region。"""

        first_style = first.style
        second_style = second.style
        if first_style is None or second_style is None:
            return True

        first_color = self._normalized_color(first_style.color)
        second_color = self._normalized_color(second_style.color)
        if first_color and second_color and first_color != second_color:
            return False
        if (
            first_style.font_weight is not None
            and second_style.font_weight is not None
            and first_style.font_weight != second_style.font_weight
        ):
            return False
        if (
            first_style.italic is not None
            and second_style.italic is not None
            and first_style.italic != second_style.italic
        ):
            return False

        first_size = first_style.font_size
        second_size = second_style.font_size
        if first_size and second_size:
            settings = self.profile.grouping
            tolerance = max(
                settings.style_font_size_tolerance_points,
                max(first_size, second_size)
                * settings.style_font_size_tolerance_ratio,
            )
            if abs(first_size - second_size) > tolerance:
                return False
        return True

    @staticmethod
    def _normalized_color(color: str | None) -> str | None:
        """归一化颜色文本，避免大小写或首尾空白造成伪差异。"""

        if color is None:
            return None
        normalized = color.strip().upper()
        if re.fullmatch(r"#[0-9A-F]{3}", normalized):
            normalized = "#" + "".join(character * 2 for character in normalized[1:])
        return normalized or None

    def _starts_new_text_item(self, block: Block) -> bool:
        """识别新编号、项目符号或冒号明细行，阻止跨条目串组。"""

        text = block.content.text if block.content else None
        return bool(text and self._TEXT_ITEM_PREFIX.match(text))

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
