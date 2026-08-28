"""按视觉连续性构建可复用的文本流。"""

from __future__ import annotations

from dataclasses import dataclass

from document_qa.schemas import BoundingBox, Page, Region, TEXT_TYPES


@dataclass(frozen=True)
class TextFlowGroup:
    """同一栏中垂直连续、样式相近的文本 Region 组。"""

    regions: tuple[Region, ...]
    bbox: BoundingBox


class TextFlowBuilder:
    """使用集中配置的几何条件构建确定性文本流。"""

    def __init__(
        self,
        *,
        line_gap_ratio: float,
        horizontal_overlap_ratio: float,
        font_size_tolerance_ratio: float,
        negative_overlap_ratio: float,
        edge_tolerance_ratio: float = 0.0,
        max_regions: int | None = None,
    ) -> None:
        """保存文本流连接条件，不在构建器内散落业务阈值。"""

        self.line_gap_ratio = line_gap_ratio
        self.horizontal_overlap_ratio = horizontal_overlap_ratio
        self.font_size_tolerance_ratio = font_size_tolerance_ratio
        self.negative_overlap_ratio = negative_overlap_ratio
        self.edge_tolerance_ratio = edge_tolerance_ratio
        self.max_regions = max_regions

    def build(self, page: Page) -> list[TextFlowGroup]:
        """按阅读顺序把文本 Region 归入唯一的视觉文本流。"""

        regions = sorted(
            (region for region in page.regions if region.type in TEXT_TYPES),
            key=lambda region: (region.bbox.y, region.bbox.x, region.id),
        )
        mutable_groups: list[list[Region]] = []
        for region in regions:
            candidates: list[tuple[float, int]] = []
            for index, group in enumerate(mutable_groups):
                if self.max_regions is not None and len(group) >= self.max_regions:
                    continue
                previous = group[-1]
                if self._can_follow(previous, region, page.width):
                    candidates.append((region.bbox.y - previous.bbox.bottom, index))
            if not candidates:
                mutable_groups.append([region])
                continue
            # 多栏交错时选择垂直距离最近的流，避免跨栏串组。
            _, best_index = min(candidates, key=lambda item: (abs(item[0]), item[1]))
            mutable_groups[best_index].append(region)

        return [
            TextFlowGroup(regions=tuple(group), bbox=self._union_bbox(group))
            for group in mutable_groups
        ]

    def _can_follow(self, previous: Region, current: Region, page_width: float) -> bool:
        """判断两个 Region 是否属于同一视觉文本流。"""

        if previous.type != current.type or current.bbox.y < previous.bbox.y:
            return False
        line_height = max(previous.bbox.height, current.bbox.height)
        gap = current.bbox.y - previous.bbox.bottom
        if gap < -line_height * self.negative_overlap_ratio:
            return False
        if gap > line_height * self.line_gap_ratio:
            return False

        overlap = max(
            0.0,
            min(previous.bbox.right, current.bbox.right)
            - max(previous.bbox.x, current.bbox.x),
        )
        overlap_ratio = overlap / min(previous.bbox.width, current.bbox.width)
        edge_distance = min(
            abs(previous.bbox.x - current.bbox.x),
            abs(previous.bbox.right - current.bbox.right),
            abs(
                previous.bbox.x
                + previous.bbox.width / 2
                - current.bbox.x
                - current.bbox.width / 2
            ),
        )
        edges_aligned = bool(
            page_width > 0
            and edge_distance / page_width <= self.edge_tolerance_ratio
        )
        if overlap_ratio < self.horizontal_overlap_ratio and not edges_aligned:
            return False

        previous_size = previous.style.font_size if previous.style else None
        current_size = current.style.font_size if current.style else None
        if previous_size and current_size:
            size_change = abs(previous_size - current_size) / max(
                previous_size, current_size
            )
            if size_change > self.font_size_tolerance_ratio:
                return False
        return True

    @staticmethod
    def _union_bbox(regions: list[Region]) -> BoundingBox:
        """计算文本流全部 Region 的最小外接矩形。"""

        x0 = min(region.bbox.x for region in regions)
        y0 = min(region.bbox.y for region in regions)
        x1 = max(region.bbox.right for region in regions)
        y1 = max(region.bbox.bottom for region in regions)
        return BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
