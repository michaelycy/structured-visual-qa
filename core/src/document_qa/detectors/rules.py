"""MVP 使用的布局、缺失和字体规则检测。"""

from typing import Any

from document_qa.detectors.alignment import (
    AlignmentDetectionResult,
    TextAlignmentDetector,
)
from document_qa.detectors.evidence import region_evidence
from document_qa.matching.geometry import (
    intersection_ratio,
    position_similarity,
    size_similarity,
)
from document_qa.profiles import (
    DetectorSettings,
    DetectorThresholds,
    RuleProfile,
    default_rule_profile,
)
from document_qa.script_detection import resolve_language
from document_qa.style_stats import weighted_median_font_size
from document_qa.text_visibility import has_visible_text
from document_qa.schemas import (
    Block,
    BoundingBox,
    ElementType,
    Issue,
    IssueType,
    Page,
    PageMatchResult,
    Region,
    RegionMatch,
    Severity,
    StructuredDiff,
    TEXT_TYPES,
)


class RuleDetector:
    """把匹配结果和目标页面转换为统一 Issue 列表。"""

    _TEXT_TYPES = TEXT_TYPES

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """初始化带版本的检测器开关和阈值。"""

        self.profile = profile or default_rule_profile()
        self.alignment_detector = TextAlignmentDetector(self.profile)

    def detect(
        self, source: Page, target: Page, match_result: PageMatchResult
    ) -> list[Issue]:
        """按确定顺序运行各规则，保证报告输出稳定。

        检测开关与阈值按语言场景解析（与 ContentDetector 共用同一
        resolve_language 逻辑），命中 language_overrides 时使用该场景
        的覆盖配置；默认 Profile 无覆盖，行为与全局配置一致。
        """

        settings = self.profile.detector_settings_for(
            resolve_language(self.profile, source.regions, target.regions)
        )
        issues: list[Issue] = []
        enabled = settings.enabled
        rasterized_issues: list[Issue] = []
        rasterized_image_ids: set[str] = set()
        rasterized_text_ids: set[str] = set()
        rasterized_pairs: set[frozenset[str]] = set()
        # 即使业务策略关闭“文本改为图片显示”提示，也要识别这种结构并
        # 抑制同一区域的新增图片、不可见文字和重叠误报。
        (
            rasterized_issues,
            rasterized_image_ids,
            rasterized_text_ids,
            rasterized_pairs,
        ) = self._detect_rasterized_text(source, target, match_result, settings)
        if enabled.text_rasterized:
            issues.extend(rasterized_issues)
        if enabled.missing_element:
            issues.extend(
                self._detect_missing(
                    source,
                    target,
                    match_result,
                    suppressed_target_ids=rasterized_image_ids,
                )
            )
        alignment_result = AlignmentDetectionResult()
        if enabled.text_alignment_changed:
            alignment_result = self.alignment_detector.detect(
                source, target, match_result, settings
            )
            issues.extend(
                issue
                for issue in alignment_result.issues
                if issue.target_region not in rasterized_text_ids
            )
        if (
            enabled.region_shifted
            or enabled.font_shrink
            or enabled.font_grow
            or enabled.region_resized
        ):
            issues.extend(
                self._detect_geometry(
                    source,
                    target,
                    match_result,
                    alignment_result,
                    suppressed_target_ids=rasterized_text_ids,
                    settings=settings,
                )
            )
        if enabled.text_fragmented:
            issues.extend(
                self._detect_fragmented(
                    target,
                    source,
                    match_result,
                    suppressed_target_ids=rasterized_text_ids,
                    settings=settings,
                )
            )
        if enabled.invisible_text:
            issues.extend(
                self._detect_invisible_text(
                    target,
                    source,
                    match_result,
                    suppressed_target_ids=rasterized_text_ids,
                    settings=settings,
                )
            )
        if enabled.content_out_of_page:
            issues.extend(self._detect_out_of_page(target, settings.thresholds))
        if enabled.overlap:
            issues.extend(
                self._detect_overlaps(
                    source,
                    target,
                    match_result,
                    suppressed_pairs=rasterized_pairs,
                    suppressed_target_ids=rasterized_text_ids,
                    settings=settings,
                )
            )
        return issues

    def _detect_missing(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        suppressed_target_ids: set[str] | None = None,
    ) -> list[Issue]:
        """识别源元素缺失和目标文档意外新增元素。"""

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        issues: list[Issue] = []
        suppressed_target_ids = suppressed_target_ids or set()
        for region_id in result.unmatched_source_region_ids:
            region = source_regions[region_id]
            if self._is_blank_text_region(region):
                continue
            is_image = region.type == ElementType.IMAGE
            # 不同语言的 PDF 导出器经常把多个英文段落合并为一个中文文本框。
            # 只要目标文本在同一版面范围内充分覆盖该源文本，就不能判为内容缺失。
            if not is_image and self._is_covered_by_target_text(region, target):
                continue
            issues.append(
                Issue(
                    id=f"p{source.page}-missing-{region_id}",
                    page=source.page,
                    type=IssueType.MISSING_IMAGE
                    if is_image
                    else IssueType.MISSING_ELEMENT,
                    severity=Severity.CRITICAL if is_image else Severity.HIGH,
                    source_region=region_id,
                    bbox=region.bbox,
                    metrics={
                        "region_type": region.type.value,
                        **region_evidence(source=region),
                    },
                    description="目标文档缺少源文档中的图片。"
                    if is_image
                    else "目标文档缺少可匹配的源区域。",
                    detector="missing-element",
                )
            )
        for region_id in result.unmatched_target_region_ids:
            if region_id in suppressed_target_ids:
                continue
            region = target_regions[region_id]
            if self._is_blank_text_region(region):
                continue
            issues.append(
                Issue(
                    id=f"p{target.page}-added-{region_id}",
                    page=target.page,
                    type=IssueType.ADDED_ELEMENT,
                    severity=Severity.LOW,
                    target_region=region_id,
                    bbox=region.bbox,
                    metrics={
                        "region_type": region.type.value,
                        **region_evidence(target=region),
                    },
                    description="目标文档出现未能与源文档匹配的新增区域。",
                    detector="missing-element",
                )
            )
        return issues

    def _detect_rasterized_text(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        settings: DetectorSettings | None = None,
    ) -> tuple[list[Issue], set[str], set[str], set[frozenset[str]]]:
        """识别“透明译文文本层 + 同位置可见图片”的局部文字栅格化。

        只使用已匹配的源/目标文本建立语义对应，再从未匹配目标图片中寻找
        高重叠证据；正常插图、图片背景叠字和仅靠位置猜测的跨类型区域不会命中。
        """

        resolved = settings or self.profile.detectors
        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        blocks_by_id = {block.id: block for block in target.blocks}
        thresholds = resolved.thresholds
        image_regions = [
            target_regions[region_id]
            for region_id in result.unmatched_target_region_ids
            if target_regions[region_id].type == ElementType.IMAGE
        ]
        candidates: list[tuple[float, Region, Region, Region, RegionMatch]] = []
        for match in result.matches:
            source_region = source_regions.get(match.source_region_id)
            target_text = target_regions.get(match.target_region_id)
            if (
                source_region is None
                or target_text is None
                or source_region.type not in self._TEXT_TYPES
                or target_text.type not in self._TEXT_TYPES
                or self._is_blank_text_region(target_text)
            ):
                continue
            opacities = self._region_opacities(target_text, blocks_by_id)
            if (
                not opacities
                or max(opacities) > thresholds.invisible_opacity_threshold
            ):
                continue
            for image_region in image_regions:
                overlap = intersection_ratio(target_text.bbox, image_region.bbox)
                if overlap >= thresholds.rasterized_image_overlap_ratio:
                    candidates.append(
                        (overlap, source_region, target_text, image_region, match)
                    )

        issues: list[Issue] = []
        claimed_text_ids: set[str] = set()
        claimed_image_ids: set[str] = set()
        suppressed_pairs: set[frozenset[str]] = set()
        for overlap, source_region, target_text, image_region, match in sorted(
            candidates, key=lambda item: (-item[0], item[2].id, item[3].id)
        ):
            if (
                target_text.id in claimed_text_ids
                or image_region.id in claimed_image_ids
            ):
                continue
            opacities = self._region_opacities(target_text, blocks_by_id)
            evidence = region_evidence(source_region, target_text, match)
            evidence.update(
                {
                    "region_type": ElementType.IMAGE.value,
                    "type_change": "text->image",
                    "text_opacity": max(opacities),
                    "image_overlap_ratio": overlap,
                    "invisible_text_region": target_text.id,
                    "invisible_text_bbox": target_text.bbox.model_dump(mode="json"),
                    "visible_image_region": image_region.id,
                    "target_bbox": image_region.bbox.model_dump(mode="json"),
                    "target_region_type": ElementType.IMAGE.value,
                }
            )
            issues.append(
                Issue(
                    id=f"p{target.page}-rasterized-{image_region.id}",
                    page=target.page,
                    type=IssueType.TEXT_RASTERIZED,
                    severity=resolved.severity_for(
                        IssueType.TEXT_RASTERIZED, Severity.HIGH
                    ),
                    source_region=source_region.id,
                    target_region=image_region.id,
                    bbox=image_region.bbox,
                    metrics=evidence,
                    description=(
                        "原文文本区域在目标文档中由图片负责可见渲染，"
                        "并保留透明文本层供检索，文字显示方式已栅格化。"
                    ),
                    detector="text-rasterization",
                )
            )
            claimed_text_ids.add(target_text.id)
            claimed_image_ids.add(image_region.id)
            suppressed_pairs.add(frozenset((target_text.id, image_region.id)))
        # 候选选择按重叠率保证一对一最优，输出再恢复 Matcher 的目标 Region
        # 原始顺序，使既有报告中的页面内问题序号尽量保持稳定。
        target_order = {
            region_id: index
            for index, region_id in enumerate(result.unmatched_target_region_ids)
        }
        issues.sort(
            key=lambda issue: target_order.get(issue.target_region or "", len(target_order))
        )
        return issues, claimed_image_ids, claimed_text_ids, suppressed_pairs

    @staticmethod
    def _region_opacities(
        region: Region, blocks_by_id: dict[str, Block]
    ) -> list[float]:
        """返回 Region 子文本 Block 中已知的归一化透明度。"""

        values: list[float] = []
        for block_id in region.children:
            block = blocks_by_id.get(block_id)
            metadata = getattr(block, "metadata", None)
            opacity = metadata.get("opacity") if metadata else None
            if isinstance(opacity, (int, float)):
                values.append(float(opacity))
        return values

    def _is_covered_by_target_text(self, source_region: Region, target: Page) -> bool:
        """判断未匹配源文本是否已被目标文本框通过多对一方式承载。"""

        return any(
            region.type in self._TEXT_TYPES
            and intersection_ratio(source_region.bbox, region.bbox)
            >= self.profile.matching.merged_text_coverage_ratio
            for region in target.regions
        )

    def _detect_geometry(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        alignment_result: AlignmentDetectionResult,
        suppressed_target_ids: set[str] | None = None,
        settings: DetectorSettings | None = None,
    ) -> list[Issue]:
        """检测显著位移、尺寸剧变与字号变化，并保留触发规则的比例。"""

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        thresholds = (settings or self.profile.detectors).thresholds
        enabled = (settings or self.profile.detectors).enabled
        suppressed_target_ids = suppressed_target_ids or set()
        matches_by_pair = {
            (match.source_region_id, match.target_region_id): match
            for match in result.matches
        }
        issues: list[Issue] = []
        for diff in result.diffs:
            if diff.target_region_id in suppressed_target_ids:
                continue
            source_region = source_regions[diff.source_region_id]
            target_region = target_regions[diff.target_region_id]
            if (
                source_region.type in self._TEXT_TYPES
            ) != (target_region.type in self._TEXT_TYPES):
                # 全局分配在两侧 Region 数量相等、译文合并多个标题时，
                # 可能用一个额外图片占住剩余文本。跨内容类别的几何量
                # 没有可比性，不能据此生成位移、尺寸或字号问题。
                continue
            # 多对一合并证据：目标 Region 实质覆盖 ≥2 个文本源 Region 时，
            # 该配对不是 1↔1 内容对应（译文把多个源块排进同一区域）。
            # 覆盖明细写入 metrics，前端据此把源图对应框展开到全部被
            # 覆盖源区域，避免"两侧框应重合"的错觉。
            merged_evidence: dict[str, Any] = {}
            covered_sources = self._covered_source_regions(
                source,
                target_region,
                min_ratio=thresholds.merged_source_overlap_ratio,
            )
            if len(covered_sources) >= 2:
                merged_evidence = {
                    "merged_source_count": len(covered_sources),
                    "covered_source_bboxes": [
                        region.bbox.model_dump(mode="json")
                        for region in covered_sources
                    ],
                }
            evidence = region_evidence(
                source_region,
                target_region,
                matches_by_pair.get(
                    (diff.source_region_id, diff.target_region_id)
                ),
            )
            shift = max(abs(diff.x_shift_ratio), abs(diff.y_shift_ratio))
            if (
                enabled.region_shifted
                and diff.target_region_id
                not in alignment_result.suppressed_shift_target_ids
                and shift > thresholds.shifted_ratio
            ):
                severity = (
                    Severity.HIGH
                    if shift > thresholds.severely_shifted_ratio
                    else Severity.MEDIUM
                )
                issues.append(
                    Issue(
                        id=f"p{target.page}-shift-{diff.target_region_id}",
                        page=target.page,
                        type=IssueType.REGION_SHIFTED,
                        severity=severity,
                        source_region=diff.source_region_id,
                        target_region=diff.target_region_id,
                        bbox=target_region.bbox,
                        metrics={
                            "x_shift_ratio": diff.x_shift_ratio,
                            "y_shift_ratio": diff.y_shift_ratio,
                            "shifted_ratio_threshold": thresholds.shifted_ratio,
                            "severely_shifted_ratio_threshold": (
                                thresholds.severely_shifted_ratio
                            ),
                            **merged_evidence,
                            **evidence,
                        },
                        description="目标区域相对源区域发生显著位置偏移。",
                        detector="geometry",
                    )
                )

            font_change = diff.font_size_change_ratio
            # 多对一合并区域：目标 Region 覆盖 ≥2 个文本源 Region（译文
            # 把多个标题/段落排进同一行）时，合并代表字号混入了不同内容，
            # 区域级缩小判断与"译文变长"豁免都失去前提。span 级对照可用
            # 时由其逐源 Region 出缩小结论并跳过区域级判断；span 证据
            # 不可用（返回 None）则回退既有逻辑。font_grow 维持原逻辑。
            merged_skip_shrink = False
            if enabled.font_shrink:
                merged_issues = self._detect_merged_font_shrink(
                    source=source,
                    target=target,
                    target_region=target_region,
                    source_region=source_region,
                    thresholds=thresholds,
                    match=matches_by_pair.get(
                        (diff.source_region_id, diff.target_region_id)
                    ),
                )
                if merged_issues is not None:
                    issues.extend(merged_issues)
                    merged_skip_shrink = True
            if (
                enabled.font_shrink
                and not merged_skip_shrink
                and font_change is not None
                and font_change < thresholds.font_shrink_ratio
            ):
                # 严重度按缩小幅度分档：轻微缩小（如 25%）是排版适配，
                # 严重缩小（如 50%）才是明显的交付风险。
                shrink_magnitude = abs(font_change)
                shrink_severity = thresholds.band_severity(
                    thresholds.font_shrink_bands,
                    shrink_magnitude,
                    Severity.HIGH,
                )
                if not (
                    shrink_severity == Severity.MEDIUM
                    and self._is_expected_translation_expansion(
                        source_region, target_region
                    )
                ):
                    issues.append(
                        Issue(
                            id=f"p{target.page}-font-{diff.target_region_id}",
                            page=target.page,
                            type=IssueType.FONT_SHRINK,
                            # 字号缩小本身需要人工复核；只有同时出现裁切、越界等
                            # 可见内容损失时，才由相应规则升级为 Critical。
                            severity=shrink_severity,
                            source_region=diff.source_region_id,
                            target_region=diff.target_region_id,
                            bbox=target_region.bbox,
                            metrics={
                                "font_size_change_ratio": font_change,
                                "font_shrink_ratio_threshold": (
                                    thresholds.font_shrink_ratio
                                ),
                                **merged_evidence,
                                **evidence,
                            },
                            description="目标区域字号为适应版面而明显缩小。",
                            detector="typography",
                        )
                    )

            # 字号放大：翻译后文字变长常触发字号膨胀，是换行爆炸的前兆。
            # 放大本身不丢失内容，严重度固定 MEDIUM（低于缩小的档位）。
            if (
                enabled.font_grow
                and font_change is not None
                and font_change > thresholds.font_grow_ratio
            ):
                issues.append(
                    Issue(
                        id=f"p{target.page}-fontgrow-{diff.target_region_id}",
                        page=target.page,
                        type=IssueType.TYPOGRAPHY_CHANGED,
                        severity=Severity.MEDIUM,
                        source_region=diff.source_region_id,
                        target_region=diff.target_region_id,
                        bbox=target_region.bbox,
                        metrics={
                            "font_size_change_ratio": font_change,
                            "font_grow_ratio_threshold": thresholds.font_grow_ratio,
                            **merged_evidence,
                            **evidence,
                        },
                        description="目标区域字号相对源区域明显放大。",
                        detector="typography",
                    )
                )

            # 尺寸剧变：宽/高变化比例超过阈值说明区域被合并或拆散
            # （如标签文本并入描述段后宽度 -80%、高度 +166%）。
            resize = max(
                abs(diff.width_change_ratio), abs(diff.height_change_ratio)
            )
            expected_text_width_change = self._is_expected_text_width_change(
                source_region, target_region, diff
            )
            expected_text_reflow = self._is_expected_text_reflow(
                source_region, target_region, diff
            )
            expected_translation_expansion = (
                self._is_expected_translation_expansion(
                    source_region, target_region
                )
            )
            if (
                enabled.region_resized
                and diff.target_region_id
                not in alignment_result.suppressed_resize_target_ids
                and not expected_text_width_change
                and not expected_text_reflow
                and not expected_translation_expansion
                and resize > thresholds.region_resize_ratio
            ):
                issues.append(
                    Issue(
                        id=f"p{target.page}-resize-{diff.target_region_id}",
                        page=target.page,
                        type=IssueType.REGION_RESIZED,
                        severity=thresholds.band_severity(
                            thresholds.region_resize_bands,
                            resize,
                            Severity.MEDIUM,
                        ),
                        source_region=diff.source_region_id,
                        target_region=diff.target_region_id,
                        bbox=target_region.bbox,
                        metrics={
                            "width_change_ratio": diff.width_change_ratio,
                            "height_change_ratio": diff.height_change_ratio,
                            "resize_magnitude": resize,
                            "region_resize_ratio_threshold": (
                                thresholds.region_resize_ratio
                            ),
                            **merged_evidence,
                            **evidence,
                        },
                        description="目标区域尺寸相对源区域剧变，可能发生段落合并或拆散。",
                        detector="geometry",
                    )
                )
        return issues

    def _covered_source_regions(
        self,
        source: Page,
        target_region: Region,
        *,
        min_ratio: float | None = None,
    ) -> list[Region]:
        """返回被目标 Region 压境的文本源 Region。

        min_ratio 缺省用 `merged_text_coverage_ratio`（实质覆盖语义，
        供 span 级字号对照的归属判定）；传入 `merged_source_overlap_ratio`
        时为宽松压境语义——合并条通常只压住各源标签的一部分，用于
        M→1 合并证据的收集。两处判定共用本方法保证口径集中。
        """

        coverage_ratio = (
            min_ratio
            if min_ratio is not None
            else self.profile.matching.merged_text_coverage_ratio
        )
        return [
            region
            for region in source.regions
            if region.type in self._TEXT_TYPES
            and not self._is_blank_text_region(region)
            and intersection_ratio(region.bbox, target_region.bbox) >= coverage_ratio
        ]

    def _detect_merged_font_shrink(
        self,
        source: Page,
        target: Page,
        target_region: Region,
        source_region: Region,
        thresholds: DetectorThresholds,
        match: RegionMatch | None,
    ) -> list[Issue] | None:
        """多对一合并区域的 span 级字号缩小对照。

        译文常把多个标题/段落排进同一行，目标 Region 因此覆盖多个源
        Region：合并代表字号混入了不同内容，区域级 diff 与"译文变长"
        豁免都失去前提（真实记录 20260831-055811 中 -25% 的标题缩小被
        豁免静默）。这里把目标 Region 的文本 span 分配回各源 Region，
        并做双向实质覆盖门控（复用 merged_text_coverage_ratio）：
        span 须大部分落在源 Region 内，源 Region 的 bbox 也须被名下
        span 实质覆盖（防擦边页码字符）——通过后按字符数加权中位数
        字号逐一对照。span 字号即该内容的实际渲染字号，无代表性歧义，
        故不适用翻译排版豁免。返回 None 表示 span 证据不可用（非多
        对一，或无带字号的可见文本 span），调用方回退既有区域级判断。
        """

        coverage_ratio = self.profile.matching.merged_text_coverage_ratio
        covered_sources = [
            region
            for region in self._covered_source_regions(source, target_region)
            if region.style is not None and region.style.font_size
        ]
        if len(covered_sources) < 2:
            return None
        blocks_by_id = {block.id: block for block in target.blocks}
        spans: list[Block] = []
        for block_id in target_region.children:
            block = blocks_by_id.get(block_id)
            text = block.content.text if block and block.content else None
            if (
                block is None
                or block.style is None
                or not block.style.font_size
                or not has_visible_text(text)
            ):
                continue
            spans.append(block)
        if not spans:
            return None
        # 每个 span 归属"实质性覆盖它的"源 Region：交集须占 span 面积
        # 的比例达到 merged_text_coverage_ratio（与多对一覆盖判定同一
        # 语义），仅按最大重叠面积会把恰好擦边的页码等小字符强行归给
        # 大标题，产生 5pt vs 30pt 的垃圾对照。
        assigned: dict[str, list[Block]] = {
            region.id: [] for region in covered_sources
        }
        for span in spans:
            best_region: Region | None = None
            best_ratio = 0.0
            for region in covered_sources:
                overlap_width = max(
                    0.0,
                    min(span.bbox.right, region.bbox.right)
                    - max(span.bbox.x, region.bbox.x),
                )
                overlap_height = max(
                    0.0,
                    min(span.bbox.bottom, region.bbox.bottom)
                    - max(span.bbox.y, region.bbox.y),
                )
                overlap_area = overlap_width * overlap_height
                span_area = span.bbox.width * span.bbox.height
                ratio = overlap_area / span_area if span_area > 0 else 0.0
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_region = region
            if best_region is not None and best_ratio >= coverage_ratio:
                assigned[best_region.id].append(span)
        issues: list[Issue] = []
        for covered in covered_sources:
            members = assigned[covered.id]
            if not members:
                continue
            # 双向覆盖门控的第二向：源 Region 的 bbox 须被其名下 span
            # 实质覆盖。仅有 span 落在源 bbox 内（如混入标题区域的页码
            # 字符）不足以证明span 是该源内容的翻译——此时字号对照无
            # 意义，直接跳过而非产出垃圾结论。
            covered_area = 0.0
            for span in members:
                overlap_width = max(
                    0.0,
                    min(span.bbox.right, covered.bbox.right)
                    - max(span.bbox.x, covered.bbox.x),
                )
                overlap_height = max(
                    0.0,
                    min(span.bbox.bottom, covered.bbox.bottom)
                    - max(span.bbox.y, covered.bbox.y),
                )
                covered_area += overlap_width * overlap_height
            source_area = covered.bbox.width * covered.bbox.height
            if source_area <= 0 or covered_area / source_area < coverage_ratio:
                continue
            span_size = weighted_median_font_size(
                [
                    (span.style.font_size, len(span.content.text or ""))
                    for span in members
                ]
            )
            source_size = covered.style.font_size
            if span_size is None or not source_size:
                continue
            change = (span_size - source_size) / source_size
            if change >= thresholds.font_shrink_ratio:
                continue
            shrink_magnitude = abs(change)
            severity = thresholds.band_severity(
                thresholds.font_shrink_bands, shrink_magnitude, Severity.HIGH
            )
            bbox_x0 = min(span.bbox.x for span in members)
            bbox_y0 = min(span.bbox.y for span in members)
            bbox_x1 = max(span.bbox.right for span in members)
            bbox_y1 = max(span.bbox.bottom for span in members)
            # 匹配证据只属于配对中的那个源 Region；其余被覆盖源 Region
            # （如未配对的第二个标题）不带 RegionMatch，避免张冠李戴。
            pair_match = match if covered.id == source_region.id else None
            issues.append(
                Issue(
                    id=f"p{target.page}-mfont-{covered.id}",
                    page=target.page,
                    type=IssueType.FONT_SHRINK,
                    severity=severity,
                    source_region=covered.id,
                    target_region=target_region.id,
                    bbox=BoundingBox(
                        x=bbox_x0,
                        y=bbox_y0,
                        width=bbox_x1 - bbox_x0,
                        height=bbox_y1 - bbox_y0,
                    ),
                    metrics={
                        "font_size_change_ratio": round(change, 4),
                        "source_font_size": source_size,
                        "span_font_size": span_size,
                        "span_count": len(members),
                        "font_shrink_ratio_threshold": thresholds.font_shrink_ratio,
                        "merged_region_compare": True,
                        "merged_source_count": len(covered_sources),
                        "covered_source_bboxes": [
                            region.bbox.model_dump(mode="json")
                            for region in covered_sources
                        ],
                        **region_evidence(covered, target_region, pair_match),
                    },
                    description=(
                        "目标区域将多个源区域合并排版，其中本区域对应文字"
                        "字号明显缩小。"
                    ),
                    detector="typography",
                )
            )
        return issues

    @classmethod
    def _is_expected_translation_expansion(
        cls, source: Region, target: Region
    ) -> bool:
        """识别译文变长且文本框未收缩的正常跨语言排版适配。"""

        if source.type not in cls._TEXT_TYPES or target.type not in cls._TEXT_TYPES:
            return False
        source_text = source.content.text if source.content else None
        target_text = target.content.text if target.content else None
        if not source_text or not target_text:
            return False
        source_chars = len("".join(source_text.split()))
        target_chars = len("".join(target_text.split()))
        if target_chars <= source_chars:
            return False
        source_area = source.bbox.width * source.bbox.height
        target_area = target.bbox.width * target.bbox.height
        return target_area >= source_area

    def _is_expected_text_width_change(
        self, source: Region, target: Region, diff: StructuredDiff
    ) -> bool:
        """识别短标签因跨语言字数变化造成的正常文字墨迹宽度变化。"""

        if source.type not in self._TEXT_TYPES or target.type not in self._TEXT_TYPES:
            return False
        source_text = source.content.text if source.content else None
        target_text = target.content.text if target.content else None
        if not source_text or not target_text:
            return False
        thresholds = self.profile.detectors.thresholds
        source_chars = len("".join(source_text.split()))
        target_chars = len("".join(target_text.split()))
        if max(source_chars, target_chars) > thresholds.text_label_max_chars:
            return False
        if (
            abs(diff.height_change_ratio)
            > thresholds.text_resize_height_tolerance_ratio
        ):
            return False
        font_change = diff.font_size_change_ratio
        if (
            font_change is not None
            and abs(font_change) > thresholds.text_resize_font_tolerance_ratio
        ):
            return False
        # 只豁免宽度驱动的变化；高度剧变仍由 Region resize 规则报告。
        return abs(diff.width_change_ratio) > abs(diff.height_change_ratio)

    def _is_expected_text_reflow(
        self, source: Region, target: Region, diff: StructuredDiff
    ) -> bool:
        """识别翻译后自然增加少量行数、但每行尺度仍稳定的文本回流。"""

        if source.type not in self._TEXT_TYPES or target.type not in self._TEXT_TYPES:
            return False
        source_text = source.content.text if source.content else None
        target_text = target.content.text if target.content else None
        if not source_text or not target_text:
            return False
        source_lines = [line for line in source_text.splitlines() if line.strip()]
        target_lines = [line for line in target_text.splitlines() if line.strip()]
        added_lines = len(target_lines) - len(source_lines)
        thresholds = self.profile.detectors.thresholds
        if added_lines <= 0 or added_lines > thresholds.text_reflow_max_added_lines:
            return False
        if (
            abs(diff.width_change_ratio)
            > thresholds.text_reflow_width_tolerance_ratio
        ):
            return False
        font_change = diff.font_size_change_ratio
        if (
            font_change is not None
            and abs(font_change) > thresholds.text_reflow_font_tolerance_ratio
        ):
            return False
        source_line_height = source.bbox.height / len(source_lines)
        target_line_height = target.bbox.height / len(target_lines)
        line_height_change = (
            target_line_height - source_line_height
        ) / source_line_height
        return (
            abs(line_height_change)
            <= thresholds.text_reflow_line_height_tolerance_ratio
        )

    def _detect_fragmented(
        self,
        target: Page,
        source: Page,
        result: PageMatchResult,
        suppressed_target_ids: set[str] | None = None,
        settings: DetectorSettings | None = None,
    ) -> list[Issue]:
        """检测目标文字被竖排/拆散成单字母碎片的排版破坏。

        典型场景：翻译后缩写（PK、SAE、ICF）在窄列中放不下，被
        逐字母竖排（"P\\nK"）或拆成多个窄 Region（"SA" + "E"）。
        判据：文本 Region 的宽度与字母数同时低于阈值——正常词语的
        Region 不会既窄又只有两三个字母。Issue 附带源区域原文，
        供界面做"原文 → 译文"对照。
        """

        thresholds = (settings or self.profile.detectors).thresholds
        suppressed_target_ids = suppressed_target_ids or set()
        source_regions = {region.id: region for region in source.regions}
        # 目标区域 → 源区域映射：碎片化目标区域匹配到的源区域文本即原文。
        source_by_target = {
            match.target_region_id: source_regions.get(match.source_region_id)
            for match in result.matches
        }
        issues: list[Issue] = []
        for region in target.regions:
            if (
                region.type not in self._TEXT_TYPES
                or region.id in suppressed_target_ids
                or self._is_blank_text_region(region)
            ):
                continue
            text = region.content.text if region.content else None
            if not text:
                continue
            letters = [ch for ch in text if ch.isalpha()]
            # 无字母的 Region（纯数字/符号）不参与碎片判定。
            if not letters:
                continue
            if (
                region.bbox.width <= thresholds.fragment_max_width
                and len(letters) <= thresholds.fragment_max_letters
            ):
                source_region = source_by_target.get(region.id)
                source_text = (
                    source_region.content.text
                    if source_region and source_region.content
                    else None
                )
                issues.append(
                    Issue(
                        id=f"p{target.page}-frag-{region.id}",
                        page=target.page,
                        type=IssueType.TEXT_FRAGMENTED,
                        severity=Severity.MEDIUM,
                        source_region=source_region.id if source_region else None,
                        target_region=region.id,
                        bbox=region.bbox,
                        metrics={
                            "text": text,
                            "source_text": source_text,
                            "target_text": text,
                            "bbox_width": region.bbox.width,
                            "letter_count": len(letters),
                            "fragment_max_width": thresholds.fragment_max_width,
                            "fragment_max_letters": thresholds.fragment_max_letters,
                            **region_evidence(source_region, region),
                        },
                        description="目标文字疑似被竖排或拆散成字母碎片（窄列排版破坏）。",
                        detector="fragmentation",
                    )
                )
        return issues

    def _detect_invisible_text(
        self,
        target: Page,
        source: Page,
        result: PageMatchResult,
        suppressed_target_ids: set[str] | None = None,
        settings: DetectorSettings | None = None,
    ) -> list[Issue]:
        """检测透明文字或文字颜色与页面背景同色的隐形文字。

        典型场景：翻译工具转换 PPT 时丢失了文字效果层（描边/阴影），
        标题白字落到白底上整行不可见。判据：
        1. 页面背景是浅色（深色背景上白字是正常设计，跳过）；
        2. Region 内所有文本 Block 的颜色都接近背景色——只要有一个
           深色 Block（如源文档常见的白字+黑字叠层），视为可见。
        Issue 附带源区域原文，供界面做"原文 → 译文"对照。
        """

        thresholds = (settings or self.profile.detectors).thresholds
        color_threshold = thresholds.invisible_color_threshold
        opacity_threshold = thresholds.invisible_opacity_threshold
        background = (target.metadata or {}).get("background_color")
        dark_boxes = (target.metadata or {}).get("dark_boxes") or []
        blocks_by_id = {block.id: block for block in target.blocks}
        suppressed_target_ids = suppressed_target_ids or set()
        source_regions = {region.id: region for region in source.regions}
        source_by_target = {
            match.target_region_id: source_regions.get(match.source_region_id)
            for match in result.matches
        }
        issues: list[Issue] = []
        for region in target.regions:
            if (
                region.type not in self._TEXT_TYPES
                or region.id in suppressed_target_ids
                or self._is_blank_text_region(region)
            ):
                continue
            opacities = self._region_opacities(region, blocks_by_id)
            is_transparent = bool(opacities) and max(opacities) <= opacity_threshold
            text_colors = [
                block.style.color
                for block_id in region.children
                for block in [blocks_by_id.get(block_id)]
                if block is not None
                and block.style is not None
                and block.style.color
            ]
            if not is_transparent:
                # 颜色判据需要明确的浅色页面背景和文字颜色；透明度判据
                # 不依赖背景，即使透明文字叠在图片上也仍然不可见。
                if (
                    not background
                    or self._min_channel(background) < color_threshold
                    or not text_colors
                    or any(
                        self._min_channel(color) < color_threshold
                        for color in text_colors
                    )
                    or self._overlaps_dark_block(
                        region,
                        dark_boxes,
                        thresholds.invisible_dark_background_overlap_ratio,
                    )
                ):
                    continue
            source_region = source_by_target.get(region.id)
            source_text = (
                source_region.content.text
                if source_region and source_region.content
                else None
            )
            target_text = region.content.text if region.content else None
            issues.append(
                Issue(
                    id=f"p{target.page}-invisible-{region.id}",
                    page=target.page,
                    type=IssueType.INVISIBLE_TEXT,
                    severity=Severity.HIGH,
                    source_region=source_region.id if source_region else None,
                    target_region=region.id,
                    bbox=region.bbox,
                    metrics={
                        "text_color": text_colors[0] if text_colors else None,
                        "background_color": background,
                        "text_opacity": max(opacities) if opacities else None,
                        "dark_background_overlap_ratio": (
                            thresholds.invisible_dark_background_overlap_ratio
                        ),
                        "text": target_text[:60] if target_text else None,
                        "source_text": source_text,
                        "target_text": target_text,
                        **region_evidence(source_region, region),
                    },
                    description=(
                        "目标文字透明度为零，视觉上不可见。"
                        if is_transparent
                        else "目标文字颜色与页面背景同色，视觉上不可见。"
                    ),
                    detector="typography",
                )
            )
        return issues

    def _overlaps_dark_block(
        self,
        region: Region,
        dark_boxes: list[dict[str, float]],
        overlap_ratio: float,
    ) -> bool:
        """按 Profile 阈值判断文字区域是否落在深色背景块或图片上。"""

        region_area = region.bbox.width * region.bbox.height
        if region_area <= 0:
            return False
        for box in dark_boxes:
            overlap_width = max(
                0.0,
                min(region.bbox.right, box["x"] + box["width"])
                - max(region.bbox.x, box["x"]),
            )
            overlap_height = max(
                0.0,
                min(region.bbox.bottom, box["y"] + box["height"])
                - max(region.bbox.y, box["y"]),
            )
            if overlap_width * overlap_height >= region_area * overlap_ratio:
                return True
        return False

    @staticmethod
    def _min_channel(hex_color: str) -> int:
        """解析 #RRGGBB 并返回 RGB 三通道最小值（越接近 255 越白）。"""

        try:
            value = int(hex_color.lstrip("#"), 16)
            red = (value >> 16) & 0xFF
            green = (value >> 8) & 0xFF
            blue = value & 0xFF
            return min(red, green, blue)
        except ValueError:
            return 0

    @staticmethod
    def _detect_out_of_page(
        target: Page, thresholds: DetectorThresholds
    ) -> list[Issue]:
        """检测区域边界超出页面可见范围（含相对页面尺寸的容差）。

        零容差判定会把字形上延、媒体框边缘的亚点级溢出判成 Critical
        并拖垮整篇结论；按轴计算溢出量，与相对页宽/页高的容差比较后
        只报告真实越界。容差与溢出量写入 metrics，保证报告能复现
        当时的判定边界。
        """

        tolerance_x = target.width * thresholds.out_of_page_tolerance_ratio
        tolerance_y = target.height * thresholds.out_of_page_tolerance_ratio
        issues: list[Issue] = []
        for region in target.regions:
            # 按轴取左右/上下两个方向的最大溢出，亚点级边缘噪声不触发。
            overflow_x = max(
                max(0.0, -region.bbox.x),
                max(0.0, region.bbox.right - target.width),
            )
            overflow_y = max(
                max(0.0, -region.bbox.y),
                max(0.0, region.bbox.bottom - target.height),
            )
            if overflow_x <= tolerance_x and overflow_y <= tolerance_y:
                continue
            issues.append(
                Issue(
                    id=f"p{target.page}-out-{region.id}",
                    page=target.page,
                    type=IssueType.CONTENT_OUT_OF_PAGE,
                    severity=Severity.CRITICAL,
                    target_region=region.id,
                    bbox=region.bbox,
                    metrics={
                        "page_width": target.width,
                        "page_height": target.height,
                        "out_of_page_tolerance_ratio": (
                            thresholds.out_of_page_tolerance_ratio
                        ),
                        "overflow_x": round(overflow_x, 2),
                        "overflow_y": round(overflow_y, 2),
                        **region_evidence(target=region),
                    },
                    description="目标区域超出页面边界，内容可能被裁切。",
                    detector="overflow",
                )
            )
        return issues

    def _detect_overlaps(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        suppressed_pairs: set[frozenset[str]] | None = None,
        suppressed_target_ids: set[str] | None = None,
        settings: DetectorSettings | None = None,
    ) -> list[Issue]:
        """只报告翻译后新增或显著加剧的区域重叠。"""

        issues: list[Issue] = []
        resolved = settings or self.profile.detectors
        thresholds = resolved.thresholds
        suppressed_pairs = suppressed_pairs or set()
        suppressed_target_ids = suppressed_target_ids or set()
        # 每个 Region 的源版面类比只需计算一次；两两组合会重复请求同一 Region。
        analog_cache: dict[str, Region | None] = {}
        source_by_id = {region.id: region for region in source.regions}
        matched_source_by_target = {
            match.target_region_id: source_by_id.get(match.source_region_id)
            for match in result.matches
        }
        regions = target.regions
        # 先按 y 轴扫描筛出 y 方向可能相交的候选对，避免 O(n²) 全量两两组合；
        # 候选对按原始索引顺序返回，报告输出顺序与全量两两组合一致。
        candidate_pairs = self._overlap_candidate_pairs(regions)
        for first_index, second_index in candidate_pairs:
            first = regions[first_index]
            second = regions[second_index]
            if first.id in suppressed_target_ids or second.id in suppressed_target_ids:
                continue
            if self._is_blank_text_region(
                first
            ) or self._is_blank_text_region(second):
                continue
            if frozenset((first.id, second.id)) in suppressed_pairs:
                continue
            if (
                first.metadata.get("source_block_index")
                == second.metadata.get("source_block_index")
                and first.metadata.get("source_component_index")
                != second.metadata.get("source_component_index")
            ):
                # 同一 PDF 原始 Block 的相邻视觉行会因字体上/下延伸导致
                # BBox 轻微相交；样式边界拆分后仍属于原生排版，不是新增重叠。
                continue
            ratio = intersection_ratio(first.bbox, second.bbox)
            if ratio <= thresholds.overlap_ratio:
                continue
            first_is_text = first.type in self._TEXT_TYPES
            second_is_text = second.type in self._TEXT_TYPES
            is_text_image = (
                first_is_text and second.type == ElementType.IMAGE
            ) or (second_is_text and first.type == ElementType.IMAGE)
            if not is_text_image and not (first_is_text and second_is_text):
                continue

            overlap_width = max(
                0.0, min(first.bbox.right, second.bbox.right)
                - max(first.bbox.x, second.bbox.x)
            )
            overlap_height = max(
                0.0, min(first.bbox.bottom, second.bbox.bottom)
                - max(first.bbox.y, second.bbox.y)
            )
            horizontal_intrusion_ratio = overlap_width / min(
                first.bbox.width, second.bbox.width
            )
            vertical_intrusion_ratio = overlap_height / min(
                first.bbox.height, second.bbox.height
            )
            if (
                first_is_text
                and second_is_text
                and min(horizontal_intrusion_ratio, vertical_intrusion_ratio)
                <= thresholds.text_overlap_axis_ratio
            ):
                continue

            source_ratio = 0.0
            source_first = matched_source_by_target.get(
                first.id
            ) or self._find_layout_analog(
                first, source, target, analog_cache, settings
            )
            source_second = matched_source_by_target.get(
                second.id
            ) or self._find_layout_analog(
                second, source, target, analog_cache, settings
            )
            if source_first is not None and source_second is not None:
                source_ratio = intersection_ratio(
                    source_first.bbox,
                    source_second.bbox,
                )
            if is_text_image:
                target_text = first if first_is_text else second
                target_image = second if first_is_text else first
                # 照片署名、版权来源和页脚通常有意叠在图片边缘；这类小型
                # 标注不属于正文侵入图片，不应产生 Critical。
                if (
                    target_text.bbox.area / (target.width * target.height)
                    <= thresholds.image_caption_area_ratio
                ):
                    continue
                source_text = source_first if first_is_text else source_second
                source_image = source_second if first_is_text else source_first
                target_center_inside = self._center_inside(
                    target_text.bbox, target_image.bbox
                )
                source_center_inside = bool(
                    source_text
                    and source_image
                    and self._center_inside(source_text.bbox, source_image.bbox)
                )
                # 图片署名和背景图叠字在源版中已经存在。面积比例会因中英文
                # 字符宽度而变化，因此以文字中心是否新进入图片作为拓扑判据。
                if not target_center_inside or source_center_inside:
                    continue
            # 背景照片、色块等常与文字天然叠放；只有目标重叠明显增加才是翻译异常。
            if ratio - source_ratio <= thresholds.overlap_increase_ratio:
                continue

            issue_type = (
                IssueType.TEXT_IMAGE_OVERLAP
                if is_text_image
                else IssueType.TEXT_OVERLAP
            )
            issues.append(
                Issue(
                    id=f"p{target.page}-overlap-{first.id}-{second.id}",
                    page=target.page,
                    type=issue_type,
                    severity=Severity.CRITICAL if is_text_image else Severity.HIGH,
                    source_region=source_first.id if source_first is not None else None,
                    target_region=first.id,
                    bbox=first.bbox,
                    metrics={
                        "overlap_ratio": ratio,
                        "horizontal_intrusion_ratio": horizontal_intrusion_ratio,
                        "vertical_intrusion_ratio": vertical_intrusion_ratio,
                        "overlap_ratio_threshold": thresholds.overlap_ratio,
                        "overlap_increase_ratio_threshold": (
                            thresholds.overlap_increase_ratio
                        ),
                        "text_overlap_axis_ratio_threshold": (
                            thresholds.text_overlap_axis_ratio
                        ),
                        "source_overlap_ratio": source_ratio,
                        "overlap_increase_ratio": ratio - source_ratio,
                        "other_region": second.id,
                        "primary_text": first.content.text if first.content else None,
                        "other_text": second.content.text if second.content else None,
                        "primary_region_type": first.type.value,
                        "other_region_type": second.type.value,
                        "other_bbox": second.bbox.model_dump(mode="json"),
                        "source_other_region": source_second.id
                        if source_second is not None
                        else None,
                        "source_other_text": source_second.content.text
                        if source_second is not None and source_second.content
                        else None,
                        "source_other_bbox": source_second.bbox.model_dump(mode="json")
                        if source_second is not None
                        else None,
                        "source_other_region_type": source_second.type.value
                        if source_second is not None
                        else None,
                        **region_evidence(source=source_first, target=first),
                    },
                    description="目标文本与图片发生明显重叠。"
                    if is_text_image
                    else "目标文本区域之间发生明显重叠。",
                    detector="overlap",
                )
            )
        return issues

    @classmethod
    def _is_blank_text_region(cls, region: Region) -> bool:
        """忽略 PDF 导出器产生的纯空白文本框，避免新增和重叠误报。"""

        if region.type not in cls._TEXT_TYPES:
            return False
        text = region.content.text if region.content else None
        return not has_visible_text(text)

    @staticmethod
    def _overlap_candidate_pairs(regions: list[Region]) -> list[tuple[int, int]]:
        """按 y 轴扫描筛出 y 方向可能相交的索引对，保持原始顺序。

        先按 y 坐标排序快速筛掉 y 方向必然不相交的组合，再把候选对按
        原始索引顺序（等价于 combinations 的顺序）输出，因此检测结果与
        输出顺序都和全量两两组合完全一致。x 方向与精确重叠比例仍由
        intersection_ratio 判定。
        """

        order = sorted(range(len(regions)), key=lambda index: regions[index].bbox.y)
        candidate_set: set[tuple[int, int]] = set()
        for position, index in enumerate(order):
            bottom = regions[index].bbox.bottom
            for later in range(position + 1, len(order)):
                other_index = order[later]
                if regions[other_index].bbox.y >= bottom:
                    # 后续 Region 的 y 单调不降，已不可能与本 Region 在 y 方向相交。
                    break
                pair = (
                    (index, other_index)
                    if index < other_index
                    else (other_index, index)
                )
                candidate_set.add(pair)
        return sorted(candidate_set)

    def _find_layout_analog(
        self,
        target_region: Region,
        source: Page,
        target: Page,
        cache: dict[str, Region | None] | None = None,
        settings: DetectorSettings | None = None,
    ) -> Region | None:
        """独立查找同类型且版面最接近的源区域，用于比较拓扑关系。"""

        resolved = settings or self.profile.detectors
        cache_key = target_region.id
        if cache is not None and cache_key in cache:
            return cache[cache_key]

        candidates = [
            region
            for region in source.regions
            if (
                region.type == target_region.type
                or (
                    region.type in self._TEXT_TYPES
                    and target_region.type in self._TEXT_TYPES
                )
            )
        ]
        analog: Region | None = None
        if candidates:

            def layout_score(candidate: Region) -> float:
                """拓扑对照更重视位置，尺寸只用于区分同位置的多个对象。"""

                weights = resolved.layout_analog_weights
                return weights.position * position_similarity(
                    candidate.bbox,
                    target_region.bbox,
                    max(source.width, target.width),
                    max(source.height, target.height),
                ) + weights.size * size_similarity(candidate.bbox, target_region.bbox)

            best = max(candidates, key=layout_score)
            if layout_score(best) >= self.profile.matching.minimum_score:
                analog = best

        if cache is not None:
            cache[cache_key] = analog
        return analog

    @staticmethod
    def _center_inside(inner: BoundingBox, outer: BoundingBox) -> bool:
        """判断第一个 BBox 的中心是否位于第二个 BBox 内部。"""

        center_x = inner.x + inner.width / 2
        center_y = inner.y + inner.height / 2
        return (
            outer.x <= center_x <= outer.right
            and outer.y <= center_y <= outer.bottom
        )
