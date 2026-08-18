"""基于版面相似度的跨页单调对齐，容忍翻译导致的整体移页。"""

from __future__ import annotations

from dataclasses import dataclass, field

from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import Document, Page, Region, TEXT_TYPES
from document_qa.matching.geometry import position_similarity, size_similarity


@dataclass(frozen=True)
class PageAlignment:
    """页对齐结果：配对页、源缺失页与目标新增页。"""

    pairs: list[tuple[int, int]] = field(default_factory=list)
    missing_source_pages: list[int] = field(default_factory=list)
    extra_target_pages: list[int] = field(default_factory=list)


class PageAligner:
    """用动态规划在页序列上求全局最优单调对齐。

    直接按页码一一配对会在翻译后文档整体移页时把后续所有页面误判为偏移。
    这里以“页版面相似度”为收益、跳页为代价，在 |页码差| 不超过窗口的
    约束下求最优单调对齐；只有当对齐明显优于按页码直配时才偏离直配结果。
    """

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """允许调用方注入版本化对齐配置。"""

        self.profile = profile or default_rule_profile()

    def align(self, source: Document, target: Document) -> PageAlignment:
        """返回源/目标文档之间的页对齐方案。"""

        settings = self.profile.alignment
        source_pages = sorted(source.pages, key=lambda page: page.page)
        target_pages = sorted(target.pages, key=lambda page: page.page)
        source_by_number = {page.page: page for page in source_pages}
        target_by_number = {page.page: page for page in target_pages}

        identity = self._identity_alignment(source_pages, target_pages)
        if not settings.enabled:
            return identity

        # 页码差超过窗口时无法配对；相似度也只需在窗口内计算。
        max_shift = settings.max_shift
        source_numbers = [page.page for page in source_pages]
        target_numbers = [page.page for page in target_pages]

        similarity: dict[tuple[int, int], float] = {}
        for source_page in source_pages:
            for target_page in target_pages:
                if abs(source_page.page - target_page.page) > max_shift:
                    continue
                similarity[(source_page.page, target_page.page)] = (
                    self._page_similarity(source_page, target_page)
                )

        best_alignment, best_score = self._dynamic_programming(
            source_numbers, target_numbers, similarity, settings.skip_penalty
        )
        identity_score = self._alignment_score(identity, similarity, settings.skip_penalty)
        # 对齐需要按“偏离直配的配对数”折算余量后才生效，防止噪声相似度
        # 引入无谓移页；缺页/多页标记是配对变化的伴生结果，不重复计数。
        deviations = len(set(best_alignment.pairs) - set(identity.pairs))
        if deviations == 0 or best_score <= identity_score + settings.shift_margin * deviations:
            return identity
        return best_alignment

    @staticmethod
    def _identity_alignment(
        source_pages: list[Page], target_pages: list[Page]
    ) -> PageAlignment:
        """按相同页码直配，并标记双方多出的页面。"""

        source_numbers = {page.page for page in source_pages}
        target_numbers = {page.page for page in target_pages}
        return PageAlignment(
            pairs=[
                (number, number) for number in sorted(source_numbers & target_numbers)
            ],
            missing_source_pages=sorted(source_numbers - target_numbers),
            extra_target_pages=sorted(target_numbers - source_numbers),
        )

    def _dynamic_programming(
        self,
        source_numbers: list[int],
        target_numbers: list[int],
        similarity: dict[tuple[int, int], float],
        skip_penalty: float,
    ) -> tuple[PageAlignment, float]:
        """经典序列对齐 DP：配对得分收益、跳页付出代价。"""

        n, m = len(source_numbers), len(target_numbers)
        if n == 0 or m == 0:
            return (
                PageAlignment(
                    missing_source_pages=list(source_numbers),
                    extra_target_pages=list(target_numbers),
                ),
                0.0,
            )

        negative = float("-inf")
        dp = [[negative] * (m + 1) for _ in range(n + 1)]
        dp[0][0] = 0.0
        for i in range(n + 1):
            for j in range(m + 1):
                if i == 0 and j == 0:
                    continue
                current = negative
                if i > 0 and dp[i - 1][j] > negative:
                    current = max(current, dp[i - 1][j] - skip_penalty)
                if j > 0 and dp[i][j - 1] > negative:
                    current = max(current, dp[i][j - 1] - skip_penalty)
                if (
                    i > 0
                    and j > 0
                    and dp[i - 1][j - 1] > negative
                    and (source_numbers[i - 1], target_numbers[j - 1]) in similarity
                ):
                    current = max(
                        current,
                        dp[i - 1][j - 1]
                        + similarity[(source_numbers[i - 1], target_numbers[j - 1])],
                    )
                dp[i][j] = current

        pairs: list[tuple[int, int]] = []
        missing: list[int] = []
        extra: list[int] = []
        i, j = n, m
        while i > 0 or j > 0:
            if (
                i > 0
                and j > 0
                and (source_numbers[i - 1], target_numbers[j - 1]) in similarity
                and dp[i][j]
                == dp[i - 1][j - 1]
                + similarity[(source_numbers[i - 1], target_numbers[j - 1])]
            ):
                pairs.append((source_numbers[i - 1], target_numbers[j - 1]))
                i, j = i - 1, j - 1
            elif i > 0 and dp[i][j] == dp[i - 1][j] - skip_penalty:
                missing.append(source_numbers[i - 1])
                i -= 1
            elif j > 0:
                extra.append(target_numbers[j - 1])
                j -= 1
            else:  # pragma: no cover - 回溯路径必然满足上述分支之一
                break
        pairs.reverse()
        missing.reverse()
        extra.reverse()
        return PageAlignment(pairs=pairs, missing_source_pages=missing,
                             extra_target_pages=extra), dp[n][m]

    @staticmethod
    def _alignment_score(
        alignment: PageAlignment,
        similarity: dict[tuple[int, int], float],
        skip_penalty: float,
    ) -> float:
        """计算某个对齐方案在相同收益函数下的总分。"""

        return (
            sum(similarity.get(pair, 0.0) for pair in alignment.pairs)
            - skip_penalty * len(alignment.missing_source_pages)
            - skip_penalty * len(alignment.extra_target_pages)
        )

    def _page_similarity(self, source: Page, target: Page) -> float:
        """对称最优匹配版面相似度，区域数量不一致自然获得低分。"""

        if not source.regions or not target.regions:
            return 1.0 if not source.regions and not target.regions else 0.0

        forward = self._best_match_average(source.regions, target, source, target)
        backward = self._best_match_average(target.regions, source, target, source)
        return (forward + backward) / 2

    def _best_match_average(
        self,
        regions: list[Region],
        other: Page,
        source: Page,
        target: Page,
    ) -> float:
        """一侧每个 Region 取对侧最优匹配得分后的平均值。"""

        scores = [
            max(
                self._region_score(region, candidate, source, target)
                for candidate in other.regions
            )
            for region in regions
        ]
        denominator = max(len(source.regions), len(target.regions))
        return sum(scores) / denominator if denominator else 0.0

    def _region_score(
        self,
        source_region: Region,
        target_region: Region,
        source: Page,
        target: Page,
    ) -> float:
        """与 RegionMatcher 同源的简化评分（不含顺序信号）。"""

        weights = self.profile.matching.weights
        if source_region.type == target_region.type:
            type_score = 1.0
        elif (
            source_region.type in TEXT_TYPES
            and target_region.type in TEXT_TYPES
        ):
            type_score = 0.8
        else:
            type_score = 0.0
        total = weights.position + weights.size + weights.type
        return (
            weights.position
            * position_similarity(
                source_region.bbox,
                target_region.bbox,
                max(source.width, target.width),
                max(source.height, target.height),
            )
            + weights.size * size_similarity(source_region.bbox, target_region.bbox)
            + weights.type * type_score
        ) / total
