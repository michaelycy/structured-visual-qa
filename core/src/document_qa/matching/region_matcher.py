"""使用全局最优分配完成同页 Region 对齐。"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from document_qa.matching.geometry import position_similarity, size_similarity
from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import (
    ElementType,
    MatchMetrics,
    Page,
    PageMatchResult,
    Region,
    RegionMatch,
    StructuredDiff,
    TEXT_TYPES,
)


class RegionMatcher:
    """综合位置、尺寸、类型和顺序进行一对一匹配。"""

    _TEXT_TYPES = TEXT_TYPES

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """允许调用方注入经过版本管理和样本校准的规则配置。"""

        self.profile = profile or default_rule_profile()

    def match_page(self, source: Page, target: Page) -> PageMatchResult:
        """构建代价矩阵，并通过线性分配获得全局最优匹配。

        页与页之间由 PageAligner 负责对齐，这里接受任意两张已对齐的页面，
        报告中的页码统一采用源页面页码。
        """

        if not source.regions or not target.regions:
            return PageMatchResult(
                page=source.page,
                unmatched_source_region_ids=[region.id for region in source.regions],
                unmatched_target_region_ids=[region.id for region in target.regions],
            )

        matrix = np.zeros((len(source.regions), len(target.regions)), dtype=float)
        metric_matrix: list[list[MatchMetrics]] = []
        for source_index, source_region in enumerate(source.regions):
            metric_row: list[MatchMetrics] = []
            for target_index, target_region in enumerate(target.regions):
                metrics = self._calculate_metrics(
                    source_region,
                    target_region,
                    source_index,
                    target_index,
                    source,
                    target,
                )
                metric_row.append(metrics)
                matrix[source_index, target_index] = 1.0 - self._score(metrics)
            metric_matrix.append(metric_row)

        source_indexes, target_indexes = linear_sum_assignment(matrix)
        matches: list[RegionMatch] = []
        diffs: list[StructuredDiff] = []
        matched_source: set[int] = set()
        matched_target: set[int] = set()

        for source_index, target_index in zip(source_indexes, target_indexes, strict=True):
            metrics = metric_matrix[int(source_index)][int(target_index)]
            score = self._score(metrics)
            # 低置信度分配不能伪装成有效匹配，应交给缺失元素检测器处理。
            if score < self.profile.matching.minimum_score:
                continue
            source_region = source.regions[int(source_index)]
            target_region = target.regions[int(target_index)]
            matches.append(
                RegionMatch(
                    page=source.page,
                    source_region_id=source_region.id,
                    target_region_id=target_region.id,
                    score=score,
                    metrics=metrics,
                )
            )
            diffs.append(self._build_diff(source_region, target_region, source))
            matched_source.add(int(source_index))
            matched_target.add(int(target_index))

        return PageMatchResult(
            page=source.page,
            matches=matches,
            diffs=diffs,
            unmatched_source_region_ids=[
                region.id
                for index, region in enumerate(source.regions)
                if index not in matched_source
            ],
            unmatched_target_region_ids=[
                region.id
                for index, region in enumerate(target.regions)
                if index not in matched_target
            ],
        )

    def _calculate_metrics(
        self,
        source_region: Region,
        target_region: Region,
        source_index: int,
        target_index: int,
        source_page: Page,
        target_page: Page,
    ) -> MatchMetrics:
        """计算组成最终匹配分数的独立可解释指标。"""

        type_score = self._type_similarity(source_region.type, target_region.type)
        source_order = source_index / max(1, len(source_page.regions) - 1)
        target_order = target_index / max(1, len(target_page.regions) - 1)
        return MatchMetrics(
            position_similarity=position_similarity(
                source_region.bbox,
                target_region.bbox,
                max(source_page.width, target_page.width),
                max(source_page.height, target_page.height),
            ),
            size_similarity=size_similarity(source_region.bbox, target_region.bbox),
            type_similarity=type_score,
            order_similarity=max(0.0, 1.0 - abs(source_order - target_order)),
        )

    def _score(self, metrics: MatchMetrics) -> float:
        """应用 Profile 权重；发布新版本前必须通过 Golden Sample 验证。"""

        weights = self.profile.matching.weights
        return (
            weights.position * metrics.position_similarity
            + weights.size * metrics.size_similarity
            + weights.type * metrics.type_similarity
            + weights.order * metrics.order_similarity
        )

    def _type_similarity(self, source: ElementType, target: ElementType) -> float:
        """允许标题与段落跨语言变化，同时阻止文本与图片误配。"""

        if source == target:
            return 1.0
        if source in self._TEXT_TYPES and target in self._TEXT_TYPES:
            return self.profile.matching.text_type_similarity
        return 0.0

    @staticmethod
    def _build_diff(
        source_region: Region, target_region: Region, source_page: Page
    ) -> StructuredDiff:
        """将绝对几何差转换为页面或源区域归一化比例。"""

        source_font_size = (
            source_region.style.font_size if source_region.style else None
        )
        target_font_size = (
            target_region.style.font_size if target_region.style else None
        )
        font_change = None
        if source_font_size and target_font_size:
            font_change = (target_font_size - source_font_size) / source_font_size

        return StructuredDiff(
            page=source_page.page,
            source_region_id=source_region.id,
            target_region_id=target_region.id,
            x_shift_ratio=(target_region.bbox.x - source_region.bbox.x)
            / source_page.width,
            y_shift_ratio=(target_region.bbox.y - source_region.bbox.y)
            / source_page.height,
            width_change_ratio=(target_region.bbox.width - source_region.bbox.width)
            / source_region.bbox.width,
            height_change_ratio=(target_region.bbox.height - source_region.bbox.height)
            / source_region.bbox.height,
            font_size_change_ratio=font_change,
            alignment_changed=(
                source_region.style is not None
                and target_region.style is not None
                and source_region.style.alignment != target_region.style.alignment
            ),
            color_changed=(
                source_region.style is not None
                and target_region.style is not None
                and source_region.style.color != target_region.style.color
            ),
        )
