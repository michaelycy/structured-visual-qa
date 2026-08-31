"""内容级确定性检测：数字一致性与漏译（未翻译）。

与布局检测同构：消费 Matcher 的配对结果 + Region 文本内容，输出统一
Issue。不使用任何模型或外部服务，跨语言判断基于确定性字符集规则。
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal

from document_qa.detectors.evidence import region_evidence
from document_qa.detectors.quantities import QuantityMention, extract_quantity_mentions
from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.script_detection import (
    ANY_SCRIPT_PATTERN,
    SCRIPT_PATTERNS,
    dominant_script,
    dominant_script_by_characters,
    resolve_language,
)
from document_qa.schemas import (
    BoundingBox,
    ElementType,
    Issue,
    IssueType,
    Page,
    PageMatchResult,
    Region,
    Severity,
    TEXT_TYPES,
)
from document_qa.text_visibility import has_visible_text, normalize_extracted_text

# 数字抽取：整数、千分位、小数的完整组合。千分位必须恰好 3 位且后随
# 数字边界（1,137.5 抽为单个 1137.5），避免把小数点后的部分切成独立 token。
_NUMBER_PATTERN = re.compile(r"\d+(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
# 数字归一化表：全角数字（中文排版）、阿拉伯-印度数字（٠-٩，阿拉伯语）
# 与扩展阿拉伯-印度数字（۰-۹，波斯/乌尔都语）统一归一为 ASCII；
# 含各自的小数点/千分位符号（U+066B/U+066C）。不做归一时同一数值会因
# 书写体系不同被判成"缺失+多余"成对误报。
_DIGIT_TRANSLATION = str.maketrans(
    "０１２３４５６７８９．，٠١٢٣٤٥٦٧٨٩٫٬۰۱۲۳۴۵۶۷۸۹",
    "0123456789.,0123456789.,0123456789",
)
# 全大写字母词（机构缩写：UNICEF、WHO、CSAM）通常保留原文不翻译。
_ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,}\b")
def _normalize_number(token: str) -> str:
    """归一化数字 token：去千分位逗号 + 去前导零（日期/页码场景）。"""

    token = token.replace(",", "")
    if "." in token:
        whole, _, fraction = token.partition(".")
        return f"{whole.lstrip('0') or '0'}.{fraction}"
    return token.lstrip("0") or "0"


class ContentDetector:
    """检查配对区域之间的数字一致性与目标文本的翻译完整性。"""

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """初始化带版本的检测开关和阈值。"""

        self.profile = profile or default_rule_profile()

    def detect(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """按固定顺序运行内容规则，保证报告输出稳定。

        检测开关与阈值按语言场景解析：profile.language 为 "auto" 时由
        文档内容推断脚本对（如 "latin-arabic"），否则直接使用声明值；
        命中 language_overrides 时用该场景的覆盖配置。
        """

        issues: list[Issue] = []
        language = resolve_language(self.profile, source.regions, target.regions)
        settings = self.profile.detector_settings_for(language)
        if settings.enabled.number_mismatch:
            issues.extend(
                self._detect_number_mismatch(source, target, result, settings)
            )
        if settings.enabled.untranslated_text:
            issues.extend(
                self._detect_untranslated(source, target, result, settings)
            )
            issues.extend(
                self._detect_untranslated_raster(source, target, result, settings)
            )
        return issues

    def _detect_untranslated_raster(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        settings,
    ) -> list[Issue]:
        """检测跨语言页面中原样保留的大面积图像化文字区域。

        该规则不猜测图片语义：只在页面主导脚本已发生变化时，聚合源目标
        内容指纹、位置和尺寸均稳定的图片 Region。单张照片、Logo 和零散
        装饰图因数量或面积不足不会命中；具体文字内容留给可选 OCR 适配层。
        """

        # 表格内大量 IGBT/SiC 等短缩写会在 Region 投票中压过正文。
        # 图像化漏译需要判断整页翻译方向，因此按可提取字符总量判断；
        # 普通文本漏译仍使用 Region 投票，保持既有混排豁免行为。
        source_script = dominant_script_by_characters(source.regions)
        target_script = dominant_script_by_characters(target.regions)
        if (
            source_script in {None, "mixed"}
            or target_script in {None, "mixed"}
            or source_script == target_script
        ):
            return []

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        source_blocks = {block.id: block for block in source.blocks}
        target_blocks = {block.id: block for block in target.blocks}
        thresholds = settings.thresholds
        unchanged_pairs: list[tuple[Region, Region]] = []
        for match in result.matches:
            source_region = source_regions.get(match.source_region_id)
            target_region = target_regions.get(match.target_region_id)
            if (
                source_region is None
                or target_region is None
                or source_region.type != ElementType.IMAGE
                or target_region.type != ElementType.IMAGE
                or match.metrics.position_similarity
                < thresholds.untranslated_raster_position_similarity
                or match.metrics.size_similarity
                < thresholds.untranslated_raster_size_similarity
            ):
                continue
            source_hashes = self._region_image_hashes(source_region, source_blocks)
            target_hashes = self._region_image_hashes(target_region, target_blocks)
            if source_hashes and source_hashes == target_hashes:
                unchanged_pairs.append((source_region, target_region))

        components = self._cluster_unchanged_images(
            unchanged_pairs,
            target.width * thresholds.untranslated_raster_cluster_x_gap_ratio,
            target.height * thresholds.untranslated_raster_cluster_y_gap_ratio,
        )
        page_area = target.width * target.height
        issues: list[Issue] = []
        for component in components:
            if len(component) < thresholds.untranslated_raster_min_images:
                continue
            source_members = [pair[0] for pair in component]
            target_members = [pair[1] for pair in component]
            source_bbox = self._union_bbox(source_members)
            target_bbox = self._union_bbox(target_members)
            bbox_area_ratio = target_bbox.width * target_bbox.height / page_area
            image_area_ratio = sum(
                region.bbox.width * region.bbox.height
                for region in target_members
            ) / page_area
            if (
                bbox_area_ratio
                < thresholds.untranslated_raster_min_bbox_area_ratio
                or image_area_ratio
                < thresholds.untranslated_raster_min_image_area_ratio
            ):
                continue
            ordered = sorted(
                component,
                key=lambda pair: (
                    pair[1].bbox.y,
                    pair[1].bbox.x,
                    pair[1].id,
                ),
            )
            anchor_source, anchor_target = ordered[0]
            index = len(issues) + 1
            issues.append(
                Issue(
                    id=f"p{target.page}-untranslated-raster-{index}",
                    page=target.page,
                    type=IssueType.UNTRANSLATED_RASTER,
                    severity=Severity.HIGH,
                    source_region=anchor_source.id,
                    target_region=anchor_target.id,
                    bbox=target_bbox,
                    metrics={
                        "source_script": source_script,
                        "target_script": target_script,
                        "unchanged_image_count": len(component),
                        "unchanged_image_bbox_area_ratio": round(
                            bbox_area_ratio, 4
                        ),
                        "unchanged_image_area_ratio": round(image_area_ratio, 4),
                        "source_bbox": source_bbox.model_dump(mode="json"),
                        "target_bbox": target_bbox.model_dump(mode="json"),
                        "source_region_ids": [pair[0].id for pair in ordered],
                        "target_region_ids": [pair[1].id for pair in ordered],
                        "ocr_status": "not_run",
                    },
                    description=(
                        "目标页面存在大面积图像化文字区域与源页面原样一致，"
                        "疑似未翻译；建议结合 OCR 或人工复核图片内文字。"
                    ),
                    detector="content-untranslated-raster",
                )
            )
        return issues

    @staticmethod
    def _region_image_hashes(
        region: Region, blocks_by_id: dict[str, object]
    ) -> tuple[str, ...]:
        """返回 Region 子图片 Block 的有序内容摘要。"""

        hashes = []
        for block_id in region.children:
            block = blocks_by_id.get(block_id)
            metadata = getattr(block, "metadata", None)
            digest = metadata.get("content_sha256") if metadata else None
            if isinstance(digest, str) and digest:
                hashes.append(digest)
        return tuple(hashes)

    @staticmethod
    def _cluster_unchanged_images(
        pairs: list[tuple[Region, Region]],
        horizontal_gap: float,
        vertical_gap: float,
    ) -> list[list[tuple[Region, Region]]]:
        """按目标侧几何邻近关系聚合未变化图片，避免把整页零散图标合并。"""

        remaining = set(range(len(pairs)))
        components: list[list[tuple[Region, Region]]] = []
        while remaining:
            seed = min(remaining)
            remaining.remove(seed)
            indexes = [seed]
            queue = [seed]
            while queue:
                current = queue.pop()
                current_bbox = pairs[current][1].bbox
                neighbors = []
                for candidate in sorted(remaining):
                    candidate_bbox = pairs[candidate][1].bbox
                    x_gap = max(
                        0.0,
                        max(current_bbox.x, candidate_bbox.x)
                        - min(current_bbox.right, candidate_bbox.right),
                    )
                    y_gap = max(
                        0.0,
                        max(current_bbox.y, candidate_bbox.y)
                        - min(current_bbox.bottom, candidate_bbox.bottom),
                    )
                    if x_gap <= horizontal_gap and y_gap <= vertical_gap:
                        neighbors.append(candidate)
                for candidate in neighbors:
                    remaining.remove(candidate)
                    indexes.append(candidate)
                    queue.append(candidate)
            components.append([pairs[index] for index in sorted(indexes)])
        return components

    @staticmethod
    def _union_bbox(regions: list[Region]) -> BoundingBox:
        """计算一组 Region 的最小外接框。"""

        x0 = min(region.bbox.x for region in regions)
        y0 = min(region.bbox.y for region in regions)
        x1 = max(region.bbox.right for region in regions)
        y1 = max(region.bbox.bottom for region in regions)
        return BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)

    def _detect_number_mismatch(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        settings=None,
    ) -> list[Issue]:
        """页面级数字集合守恒检查：总量不一致才报告，附差集明细。

        翻译中数字位置常在配对 Region 间移动（页眉日期 vs 正文年份），
        逐对比较会误报互换；页面级守恒只捕获真实的错漏译。
        页面整体移页（源/目标页码不同）时，页眉/页脚中的页码、章节号
        随页码自然变化属于排版预期，完全位于豁免带内的区域不参与
        守恒比较；非移页页对的页眉页脚数字天然一致，行为不变。
        """

        # 阈值取调用方已按语言场景解析的配置，避免重复做脚本投票。
        thresholds = (settings or self.profile.detectors).thresholds
        band_ratio = (
            thresholds.number_mismatch_margin_band_ratio
            if source.page != target.page
            else 0.0
        )
        source_numbers, source_labels, source_excluded = self._collect_numbers(
            source, band_ratio
        )
        target_numbers, target_labels, target_excluded = self._collect_numbers(
            target, band_ratio
        )
        if not source_numbers and not target_numbers:
            return []
        missing = source_numbers - target_numbers
        extra = target_numbers - source_numbers
        if not missing and not extra:
            return []
        # 定位必须在目标侧：契约要求 Issue 的 bbox 为 Target BBox，
        # 前端红框画在目标页渲染图上，拿源区域坐标会指到错误位置。
        # 优先找包含多余数字的目标区域（错译的数字就在那里）；
        # 只有缺失时，把含缺失数字的源区域经匹配结果映射到对应目标区域。
        extra_anchor = self._find_number_anchor(target, extra)
        source_anchor = self._find_number_anchor(source, missing)
        target_region = extra_anchor or self._map_to_target(
            source_anchor, target, result
        )
        # 严重度按差异数字总量分档：丢 1 个与丢 10 个不应同罪。
        diff_count = sum(missing.values()) + sum(extra.values())
        severity = thresholds.band_severity(
            thresholds.number_mismatch_bands, diff_count, Severity.HIGH
        )
        # 差异明细直接写进描述，界面列表不展开也能看到具体数字；
        # 数量类差异附换算后绝对值（0.57亿元 vs 0.57 billion yuan 这类
        # 单位混淆从原始表达式肉眼看不出 10 倍差）。
        detail_parts = []
        missing_display = self._humanized_displays(missing, source_labels)
        extra_display = self._humanized_displays(extra, target_labels)
        if missing:
            detail_parts.append(
                "缺失数字：" + "、".join(missing_display)
            )
        if extra:
            detail_parts.append(
                "多余数字：" + "、".join(extra_display)
            )
        hint = self._conversion_ratio_hint(missing, extra)
        if hint:
            detail_parts.append(hint)
        # 豁免带比例必须随 Issue 落盘（阈值可复现）；被豁免的数字在
        # 确实发生豁免时如实记录，供复核判断是否误放。
        exempt_evidence = (
            {
                "excluded_margin_numbers_source": source_excluded,
                "excluded_margin_numbers_target": target_excluded,
            }
            if source_excluded or target_excluded
            else {}
        )
        return [
            Issue(
                id=f"p{target.page}-numbers",
                page=target.page,
                type=IssueType.NUMBER_MISMATCH,
                severity=severity,
                source_region=source_anchor.id if source_anchor else None,
                target_region=target_region.id if target_region else None,
                bbox=target_region.bbox if target_region else None,
                metrics={
                    "source_numbers": self._display_numbers(
                        source_numbers, source_labels
                    ),
                    "target_numbers": self._display_numbers(
                        target_numbers, target_labels
                    ),
                    "missing_numbers": missing_display,
                    "extra_numbers": extra_display,
                    "normalized_source_numbers": sorted(source_numbers.elements()),
                    "normalized_target_numbers": sorted(target_numbers.elements()),
                    "diff_count": diff_count,
                    "margin_band_ratio": band_ratio,
                    **exempt_evidence,
                    **region_evidence(source_anchor, target_region),
                },
                description=(
                    "目标页面数字与源页面不一致，可能存在错漏译。"
                    + "（" + "；".join(detail_parts) + "）"
                ),
                detector="content-numbers",
            )
        ]

    @staticmethod
    def _find_number_anchor(
        page: Page, numbers: Counter
    ) -> Region | None:
        """找到包含指定数字集合的区域，用于问题定位。"""

        for region in page.regions:
            if ContentDetector._extract_numbers(region) & numbers:
                return region
        return None

    @classmethod
    def _collect_numbers(
        cls, page: Page, margin_band_ratio: float = 0.0
    ) -> tuple[Counter, dict[str, list[str]], list[str]]:
        """汇总页面数量键，并保留每个规范值对应的原文表达。

        margin_band_ratio > 0 时，完全位于页面顶部/底部豁免带内的
        区域（页眉/页脚）不参与守恒，其数字以原文表达返回，供
        metrics 如实记录豁免行为。
        """

        numbers: Counter = Counter()
        labels: dict[str, list[str]] = {}
        excluded: list[str] = []
        band_height = page.height * margin_band_ratio
        for region in page.regions:
            if band_height > 0 and cls._in_margin_band(
                region, page.height, band_height
            ):
                excluded.extend(
                    mention.display
                    for mention in cls._extract_number_mentions(region)
                )
                continue
            for mention in cls._extract_number_mentions(region):
                numbers[mention.key] += 1
                labels.setdefault(mention.key, []).append(mention.display)
        return numbers, labels, excluded

    @staticmethod
    def _in_margin_band(
        region: Region, page_height: float, band_height: float
    ) -> bool:
        """判断区域是否完全落入页面上端或下端的豁免带。

        必须整体包含在带内：起始于带内但向正文延伸的段落不受豁免，
        只有页眉/页脚这类独立短行才满足条件。
        """

        return (
            region.bbox.bottom <= band_height
            or region.bbox.y >= page_height - band_height
        )

    @classmethod
    def _display_numbers(
        cls, numbers: Counter, labels: dict[str, list[str]]
    ) -> list[str]:
        """把规范数量键还原为报告中可读的原文表达。"""

        return [
            display for _key, display in cls._display_entries(numbers, labels)
        ]

    @staticmethod
    def _display_entries(
        numbers: Counter, labels: dict[str, list[str]]
    ) -> list[tuple[str, str]]:
        """返回 (规范键, 原文表达) 差异明细；供原始渲染与换算标注共用。"""

        entries: list[tuple[str, str]] = []
        for key in sorted(numbers):
            available = labels.get(key, [])
            count = numbers[key]
            for display in available[:count]:
                entries.append((key, display))
            entries.extend((key, key) for _ in range(max(0, count - len(available))))
        return entries

    @classmethod
    def _humanized_displays(
        cls, numbers: Counter, labels: dict[str, list[str]]
    ) -> list[str]:
        """渲染差异明细；数量类键附加换算后绝对值，便于肉眼比较量级。

        原始表达式（如 0.57亿元 与 0.57 billion yuan）无法直接看出单位
        换算差异；绝对值用千分位数字呈现（57,000,000 vs 570,000,000），
        不依赖任何语言的单位词，跨语言场景通用。百分比与月份本身可直接
        比较，不附加换算。
        """

        humanized: list[str] = []
        for key, display in cls._display_entries(numbers, labels):
            if key.startswith("quantity:"):
                converted = f"{Decimal(key.removeprefix('quantity:')):,}"
                humanized.append(f"{display} → {converted}")
            else:
                humanized.append(display)
        return humanized

    @staticmethod
    def _conversion_ratio_hint(missing: Counter, extra: Counter) -> str:
        """单一数量键两侧各差一条且恰为 10^n 倍时，给出单位换算错误提示。

        亿元↔billion 这类单位混淆恰好放大/缩小 10 倍；这是数字一致性
        检测最高频的真实错译形态，值得在描述中直接点破。多键差异或
        非 10^n 倍不做推断，避免描述越权下结论。
        """

        missing_keys = [key for key in missing if key.startswith("quantity:")]
        extra_keys = [key for key in extra if key.startswith("quantity:")]
        if len(missing_keys) != 1 or len(extra_keys) != 1:
            return ""
        if sum(missing.values()) != 1 or sum(extra.values()) != 1:
            return ""
        source_value = Decimal(missing_keys[0].removeprefix("quantity:"))
        target_value = Decimal(extra_keys[0].removeprefix("quantity:"))
        if source_value <= 0 or target_value <= 0:
            return ""
        for times in (10, 100, 1000, 10000, 100000, 1000000):
            if target_value == source_value * times:
                return f"两者换算后相差 {times} 倍，疑似单位换算错误"
            if source_value == target_value * times:
                return f"两者换算后相差 {times} 倍，疑似单位换算错误"
        return ""

    @staticmethod
    def _map_to_target(
        source_region: Region | None,
        target: Page,
        result: PageMatchResult,
    ) -> Region | None:
        """把源锚点区域经匹配结果映射为目标区域（缺失数字只存在于源侧）。

        返回 None 表示该源区域未匹配（如目标侧整块缺失），
        此时 Issue 不带 bbox，退化为页面级提示。
        """

        if source_region is None:
            return None
        target_ids = {
            match.target_region_id
            for match in result.matches
            if match.source_region_id == source_region.id
        }
        for region in target.regions:
            if region.id in target_ids:
                return region
        return None

    def _detect_untranslated(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        settings=None,
    ) -> list[Issue]:
        """目标文本框仍大量保留源语言文字时判为漏译。

        判据是"源语言为主、目标语言占比极低"：以源页面主导脚本为参照，
        目标区域中源脚本字母占比超过阈值即判为未翻译。脚本识别通用化
        后同一判据适用于任意语言对（中英、中阿、俄英……）。
        """

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        source_script = dominant_script(list(source_regions.values()))
        target_script = dominant_script(list(target_regions.values()))
        if (
            source_script == target_script
            or source_script is None
            or source_script == "mixed"
        ):
            # 双语同文、源语言无法判定、或源页面本身混排（中英对照的
            # 目录/封面页）时跳过——混排源无法定义"未翻译"参照，
            # 强行判定会产生整页假阳性。
            return []
        # 阈值取当前语言场景解析后的配置（language_overrides 可覆盖）。
        thresholds = (
            settings or self.profile.detector_settings_for("default")
        ).thresholds
        threshold = thresholds.untranslated_ratio
        min_letters = thresholds.untranslated_min_letters
        pattern = SCRIPT_PATTERNS[source_script]
        issues: list[Issue] = []
        for match in result.matches:
            source_region = source_regions.get(match.source_region_id)
            target_region = target_regions.get(match.target_region_id)
            if source_region is None or target_region is None:
                continue
            if target_region.type not in TEXT_TYPES:
                continue
            text = target_region.content.text if target_region.content else None
            if not has_visible_text(text):
                continue
            # 机构名、版权行（© WHO、© UNFPA）本来就保留原文；
            # 字母字符过少或全由大写缩写构成的短文本不参与漏译判定。
            letters = ANY_SCRIPT_PATTERN.findall(text)
            if len(letters) < min_letters:
                continue
            without_acronyms = _ACRONYM_PATTERN.sub("", text)
            remaining = ANY_SCRIPT_PATTERN.findall(without_acronyms)
            if len(remaining) < min_letters:
                continue
            ratio = len(pattern.findall(text)) / len(letters)
            if ratio >= threshold:
                # 严重度按源语言占比分档：占比越高越接近整段漏译。
                severity = thresholds.band_severity(
                    thresholds.untranslated_bands, ratio, Severity.HIGH
                )
                issues.append(
                    Issue(
                        id=f"p{target.page}-untranslated-{target_region.id}",
                        page=target.page,
                        type=IssueType.UNTRANSLATED_TEXT,
                        severity=severity,
                        source_region=source_region.id,
                        target_region=target_region.id,
                        bbox=target_region.bbox,
                        metrics={
                            "source_script": source_script,
                            "source_language_ratio": round(ratio, 3),
                            "threshold": threshold,
                            "sample": text[:60],
                            # 原文 → 译文对照：源区域文本是应该出现的译文
                            # 来源，目标文本是疑似漏译的原文残留。
                            "source_text": source_region.content.text
                            if source_region.content
                            else None,
                            "target_text": text,
                            **region_evidence(source_region, target_region, match),
                        },
                        description="目标文本区仍保留源语言内容，疑似漏译。",
                        detector="content-untranslated",
                    )
                )
        return issues

    @staticmethod
    def _extract_numbers(region: Region) -> Counter:
        """抽取区域文本中的数字（千分位归一化：1,137 与 1137 等价）。

        中文排版常去掉千分位逗号，格式差异不应判为数字错漏；
        全角与阿拉伯-印度数字先归一；前导零去除以对齐日期类写法（01-05 与 1-5）。
        """

        text = region.content.text if region.content else None
        if not has_visible_text(text):
            return Counter()
        return Counter(
            mention.key for mention in ContentDetector._extract_number_mentions(region)
        )

    @staticmethod
    def _extract_number_mentions(region: Region) -> list[QuantityMention]:
        """提取语义数量；已归一的表达不再重复进入裸数字集合。"""

        text = region.content.text if region.content else None
        if not has_visible_text(text):
            return []
        normalized = normalize_extracted_text(text).translate(_DIGIT_TRANSLATION)
        mentions = extract_quantity_mentions(normalized)
        masked = list(normalized)
        for mention in mentions:
            for index in range(*mention.span):
                masked[index] = " "
        plain_text = "".join(masked)
        for match in _NUMBER_PATTERN.finditer(plain_text):
            value = _normalize_number(match.group(0))
            mentions.append(
                QuantityMention(key=value, display=value, span=match.span())
            )
        return sorted(mentions, key=lambda item: item.span)
