"""把不同 PDF Block 粒度规范化为稳定的逻辑文本 Region。"""

from __future__ import annotations

from collections import defaultdict

from document_qa.matching.geometry import intersection_ratio
from document_qa.matching.text_flow import TextFlowBuilder, TextFlowGroup
from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import Content, Page, Region, RegionRelationships, TEXT_TYPES


class LogicalRegionComposer:
    """为匹配和检测构造视觉连续的逻辑 Region 页面视图。"""

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """使用 RuleProfile 中的逻辑分组设置初始化组合器。"""

        self.profile = profile or default_rule_profile()

    def compose_pair(self, source: Page, target: Page) -> tuple[Page, Page]:
        """只组合在双侧几何对应图中形成 M↔N 关系的文本流。"""

        settings = self.profile.matching.logical_grouping
        if not settings.enabled:
            return source, target
        builder = TextFlowBuilder(
            line_gap_ratio=settings.line_gap_ratio,
            horizontal_overlap_ratio=settings.horizontal_overlap_ratio,
            font_size_tolerance_ratio=settings.font_size_tolerance_ratio,
            edge_tolerance_ratio=settings.edge_tolerance_ratio,
            max_regions=settings.max_regions,
        )
        source_regions = {
            region.id: region for region in source.regions if region.type in TEXT_TYPES
        }
        target_regions = {
            region.id: region for region in target.regions if region.type in TEXT_TYPES
        }
        graph: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
        for source_region in source_regions.values():
            for target_region in target_regions.values():
                if source_region.type != target_region.type:
                    continue
                if (
                    intersection_ratio(source_region.bbox, target_region.bbox)
                    < settings.counterpart_overlap_ratio
                ):
                    continue
                source_node = ("source", source_region.id)
                target_node = ("target", target_region.id)
                graph[source_node].add(target_node)
                graph[target_node].add(source_node)

        source_groups: list[tuple[TextFlowGroup, str]] = []
        target_groups: list[tuple[TextFlowGroup, str]] = []
        remaining = set(graph)
        while remaining:
            seed = min(remaining)
            remaining.remove(seed)
            component = {seed}
            queue = [seed]
            while queue:
                current = queue.pop()
                for candidate in sorted(graph[current]):
                    if candidate in component:
                        continue
                    component.add(candidate)
                    remaining.discard(candidate)
                    queue.append(candidate)

            source_members = [
                source_regions[region_id]
                for side, region_id in component
                if side == "source"
            ]
            target_members = [
                target_regions[region_id]
                for side, region_id in component
                if side == "target"
            ]
            # 样式边界拆出的相邻组件容易因 PDF 字形框交叠形成局部多解；
            # 两侧数量相同时按阅读顺序锁定，不再交给全页分配交换条目。
            if len(source_members) == len(target_members) and any(
                self._is_source_block_split(region)
                for region in (*source_members, *target_members)
            ):
                for source_member, target_member in zip(
                    sorted(
                        source_members,
                        key=lambda region: (region.bbox.y, region.bbox.x, region.id),
                    ),
                    sorted(
                        target_members,
                        key=lambda region: (region.bbox.y, region.bbox.x, region.id),
                    ),
                    strict=True,
                ):
                    pair_key = f"{source_member.id}=>{target_member.id}"
                    source_groups.append(
                        (
                            TextFlowGroup(
                                regions=(source_member,), bbox=source_member.bbox
                            ),
                            pair_key,
                        )
                    )
                    target_groups.append(
                        (
                            TextFlowGroup(
                                regions=(target_member,), bbox=target_member.bbox
                            ),
                            pair_key,
                        )
                    )
                continue
            # 普通 1↔1 无需重建；超大连通分量保守退回原子匹配，避免整栏吞并。
            if len(source_members) == len(target_members) == 1:
                continue
            if (
                not source_members
                or not target_members
                or len(source_members) > settings.max_regions
                or len(target_members) > settings.max_regions
            ):
                continue
            source_flow = self._single_flow(source, source_members, builder)
            target_flow = self._single_flow(target, target_members, builder)
            if source_flow is None or target_flow is None:
                continue
            # 同一连通分量两侧共享内部键，确保后续全局分配不会把已确认的
            # 逻辑组拆开并牵连远端 Region 重新配对。
            pair_key = "|".join(
                sorted(region.id for region in source_members)
            ) + "=>" + "|".join(sorted(region.id for region in target_members))
            source_groups.append((source_flow, pair_key))
            target_groups.append((target_flow, pair_key))

        return (
            self._compose_page(source, source_groups),
            self._compose_page(target, target_groups),
        )

    @staticmethod
    def _is_source_block_split(region: Region) -> bool:
        """判断 Region 是否来自一个被样式或空间边界拆开的原始 Block。"""

        count = region.metadata.get("_source_block_component_count")
        return isinstance(count, int) and count > 1

    @staticmethod
    def _single_flow(
        page: Page,
        regions: list[Region],
        builder: TextFlowBuilder,
    ) -> TextFlowGroup | None:
        """确认连通分量在本侧确实构成一个连续文本流。"""

        candidate_page = page.model_copy(update={"regions": regions})
        groups = builder.build(candidate_page)
        return groups[0] if len(groups) == 1 else None

    def _compose_page(
        self, page: Page, groups: list[tuple[TextFlowGroup, str]]
    ) -> Page:
        """将选中的互斥文本流写入逻辑页面视图。"""

        grouped_ids = {
            region.id for group, _pair_key in groups for region in group.regions
        }
        regions = [
            self._compose_group(page.page, group, pair_key)
            for group, pair_key in groups
        ]
        regions.extend(region for region in page.regions if region.id not in grouped_ids)
        regions.sort(key=lambda region: (region.bbox.y, region.bbox.x, region.id))
        regions = self._attach_relationships(regions)
        return page.model_copy(update={"regions": regions})

    def _compose_group(
        self, page_number: int, group: TextFlowGroup, pair_key: str
    ) -> Region:
        """把一个文本流转换为可追溯的逻辑 Region。"""

        if len(group.regions) == 1:
            region = group.regions[0]
            return region.model_copy(
                update={
                    "metadata": {
                        **region.metadata,
                        "_logical_pair_key": pair_key,
                    }
                }
            )

        members = list(group.regions)
        representative = max(
            members,
            key=lambda region: region.style.font_size
            if region.style and region.style.font_size
            else 0,
        )
        atomic_ids = [region.id for region in members]
        member_token = "-".join(
            region_id.removeprefix(f"p{page_number}-") for region_id in atomic_ids
        )
        children = list(
            dict.fromkeys(
                block_id for region in members for block_id in region.children
            )
        )
        text = "\n".join(
            region.content.text
            for region in members
            if region.content and region.content.text
        )
        return Region(
            id=f"p{page_number}-lg-{member_token}",
            page=page_number,
            type=representative.type,
            bbox=group.bbox,
            style=representative.style,
            content=Content(text=text),
            children=children,
            metadata={
                "logical_group": True,
                "atomic_region_ids": atomic_ids,
                "atomic_region_count": len(atomic_ids),
                "grouping_reason": "continuous_text_flow",
                "_logical_pair_key": pair_key,
                # 仅供对齐检测恢复原子行，不进入 QAReport。
                "_logical_atomic_regions": [
                    region.model_dump(mode="json") for region in members
                ],
            },
        )

    @staticmethod
    def _attach_relationships(regions: list[Region]) -> list[Region]:
        """按规范化后的阅读顺序重建直接邻接关系。"""

        updated = []
        for index, region in enumerate(regions):
            updated.append(
                region.model_copy(
                    update={
                        "relationships": RegionRelationships(
                            above=regions[index - 1].id if index else None,
                            below=regions[index + 1].id
                            if index + 1 < len(regions)
                            else None,
                        )
                    }
                )
            )
        return updated
