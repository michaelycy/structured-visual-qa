"""基于文本行边缘稳定性检测段落水平对齐方式变化。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from document_qa.detectors.evidence import region_evidence
from document_qa.matching.text_flow import TextFlowBuilder
from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import (
    BoundingBox,
    HorizontalAlignment,
    Issue,
    IssueType,
    Page,
    PageMatchResult,
    Region,
    Severity,
)


@dataclass(frozen=True)
class AlignmentTextFlowGroup:
    """带水平对齐推断结果的临时文本流。"""

    regions: tuple[Region, ...]
    bbox: BoundingBox
    alignment: HorizontalAlignment | None
    spreads: dict[str, float] = field(default_factory=dict)


@dataclass
class AlignmentDetectionResult:
    """对齐检测结果及需从行级几何检测中抑制的目标 Region。"""

    issues: list[Issue] = field(default_factory=list)
    suppressed_shift_target_ids: set[str] = field(default_factory=set)
    suppressed_resize_target_ids: set[str] = field(default_factory=set)


class TextAlignmentDetector:
    """把行级 Region 聚成文本流，检测 LEFT/RIGHT/CENTER 的变化。"""

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """初始化集中配置的文本流分组与对齐推断阈值。"""

        self.profile = profile or default_rule_profile()

    def detect(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> AlignmentDetectionResult:
        """比较源/目标文本流对齐方式，并返回重复几何问题抑制集合。"""

        source_groups = self._build_groups(source)
        target_groups = self._build_groups(target)
        source_by_region = self._group_index(source_groups, source)
        target_by_region = self._group_index(target_groups, target)

        pair_counts: Counter[tuple[int, int]] = Counter()
        source_match_totals: Counter[int] = Counter()
        matches_by_source_group: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for match in result.matches:
            source_index = source_by_region.get(match.source_region_id)
            target_index = target_by_region.get(match.target_region_id)
            if source_index is None or target_index is None:
                continue
            pair_counts[(source_index, target_index)] += 1
            source_match_totals[source_index] += 1
            matches_by_source_group[source_index].append(
                (match.target_region_id, target_index)
            )

        thresholds = self.profile.detectors.thresholds
        # 先按支持票数和占比选择唯一文本流配对；多数关系能吸收翻译导致的
        # 行数变化，同时识别一对一 Matcher 产生的少量跨段离群配对。
        candidates = sorted(
            pair_counts.items(),
            key=lambda item: (
                -item[1],
                -item[1] / source_match_totals[item[0][0]],
                item[0],
            ),
        )
        paired_source: set[int] = set()
        paired_target: set[int] = set()
        detection = AlignmentDetectionResult()
        for (source_index, target_index), count in candidates:
            if source_index in paired_source or target_index in paired_target:
                continue
            ratio = count / source_match_totals[source_index]
            if ratio < thresholds.alignment_group_match_ratio:
                continue
            source_group = source_groups[source_index]
            target_group = target_groups[target_index]
            paired_source.add(source_index)
            paired_target.add(target_index)
            if (
                source_group.alignment is None
                or target_group.alignment is None
                or source_group.alignment == target_group.alignment
            ):
                continue

            target_ids = {region.id for region in target_group.regions}
            detection.suppressed_shift_target_ids.update(target_ids)
            detection.suppressed_resize_target_ids.update(target_ids)
            # 同一源段落中少数被一对一分配到其他目标段落的行属于流内离群值；
            # 它们不能再作为独立位移/缩放证据重复影响评分。
            for target_region_id, matched_target_index in matches_by_source_group[
                source_index
            ]:
                if matched_target_index != target_index:
                    detection.suppressed_shift_target_ids.add(target_region_id)
                    detection.suppressed_resize_target_ids.add(target_region_id)

            detection.issues.append(
                Issue(
                    id=(
                        f"p{target.page}-alignment-"
                        f"{target_group.regions[0].id}-{target_group.regions[-1].id}"
                    ),
                    page=target.page,
                    type=IssueType.TEXT_ALIGNMENT_CHANGED,
                    severity=Severity.HIGH,
                    source_region=source_group.regions[0].id,
                    target_region=target_group.regions[0].id,
                    bbox=target_group.bbox,
                    metrics={
                        "source_alignment": source_group.alignment.value,
                        "target_alignment": target_group.alignment.value,
                        "source_line_count": len(source_group.regions),
                        "target_line_count": len(target_group.regions),
                        "source_spreads": source_group.spreads,
                        "target_spreads": target_group.spreads,
                        "group_match_count": count,
                        "group_match_ratio": ratio,
                        **region_evidence(
                            source_group.regions[0],
                            target_group.regions[0],
                        ),
                    },
                    description=(
                        "目标段落水平对齐方式由"
                        f"{source_group.alignment.value}变为"
                        f"{target_group.alignment.value}，与源版式不一致。"
                    ),
                    detector="text-alignment",
                )
            )
        detection.issues.sort(key=lambda issue: (issue.bbox.y if issue.bbox else 0, issue.id))
        return detection

    def _build_groups(self, page: Page) -> list[AlignmentTextFlowGroup]:
        """按栏位、行距和字号把文本 Region 聚成临时段落流。"""

        expanded_regions: list[Region] = []
        for region in page.regions:
            atomic_payloads = region.metadata.get("_logical_atomic_regions")
            if isinstance(atomic_payloads, list) and atomic_payloads:
                expanded_regions.extend(
                    Region.model_validate(payload) for payload in atomic_payloads
                )
            else:
                expanded_regions.append(region)
        expanded_page = page.model_copy(update={"regions": expanded_regions})
        thresholds = self.profile.detectors.thresholds
        builder = TextFlowBuilder(
            line_gap_ratio=thresholds.alignment_line_gap_ratio,
            horizontal_overlap_ratio=thresholds.alignment_horizontal_overlap_ratio,
            font_size_tolerance_ratio=(
                thresholds.alignment_font_size_tolerance_ratio
            ),
            negative_overlap_ratio=thresholds.alignment_negative_overlap_ratio,
        )
        groups: list[AlignmentTextFlowGroup] = []
        for group in builder.build(expanded_page):
            regions_in_group = list(group.regions)
            alignment, spreads = self._infer_alignment(regions_in_group, page.width)
            groups.append(
                AlignmentTextFlowGroup(
                    regions=tuple(regions_in_group),
                    bbox=group.bbox,
                    alignment=alignment,
                    spreads=spreads,
                )
            )
        return groups

    def _infer_alignment(
        self, regions: list[Region], page_width: float
    ) -> tuple[HorizontalAlignment | None, dict[str, float]]:
        """用左边缘、右边缘和中心线的归一化极差推断对齐方式。"""

        thresholds = self.profile.detectors.thresholds
        if len(regions) < thresholds.alignment_min_lines or page_width <= 0:
            return None, {}
        values = {
            HorizontalAlignment.LEFT: [region.bbox.x for region in regions],
            HorizontalAlignment.RIGHT: [region.bbox.right for region in regions],
            HorizontalAlignment.CENTER: [
                region.bbox.x + region.bbox.width / 2 for region in regions
            ],
        }
        spreads_by_alignment = {
            alignment: (max(edges) - min(edges)) / page_width
            for alignment, edges in values.items()
        }
        ordered = sorted(
            spreads_by_alignment.items(), key=lambda item: (item[1], item[0].value)
        )
        best_alignment, best_spread = ordered[0]
        confidence = ordered[1][1] - best_spread
        spreads = {
            alignment.value: round(spread, 6)
            for alignment, spread in spreads_by_alignment.items()
        }
        spreads["confidence"] = round(confidence, 6)
        if best_spread > thresholds.alignment_edge_tolerance_ratio:
            return None, spreads
        if confidence < thresholds.alignment_confidence_margin:
            return None, spreads
        return best_alignment, spreads

    @staticmethod
    def _group_index(
        groups: list[AlignmentTextFlowGroup], page: Page
    ) -> dict[str, int]:
        """建立 Region ID 到临时文本流索引的映射。"""

        indexes = {
            region.id: index
            for index, group in enumerate(groups)
            for region in group.regions
        }
        for region in page.regions:
            atomic_ids = region.metadata.get("atomic_region_ids")
            if not isinstance(atomic_ids, list) or not atomic_ids:
                continue
            member_indexes = {
                indexes[atomic_id]
                for atomic_id in atomic_ids
                if isinstance(atomic_id, str) and atomic_id in indexes
            }
            if len(member_indexes) == 1:
                indexes[region.id] = next(iter(member_indexes))
        return indexes
