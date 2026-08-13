"""MVP 使用的布局、缺失和字体规则检测。"""

from itertools import combinations

from document_qa.config import QAThresholds
from document_qa.matching.geometry import (
    intersection_ratio,
    position_similarity,
    size_similarity,
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
)


class RuleDetector:
    """把匹配结果和目标页面转换为统一 Issue 列表。"""

    _TEXT_TYPES = {
        ElementType.TEXT,
        ElementType.PARAGRAPH,
        ElementType.HEADING,
        ElementType.LIST,
        ElementType.HEADER,
        ElementType.FOOTER,
    }

    def __init__(self, thresholds: QAThresholds | None = None) -> None:
        """初始化集中管理的检测阈值。"""

        self.thresholds = thresholds or QAThresholds()

    def detect(
        self, source: Page, target: Page, match_result: PageMatchResult
    ) -> list[Issue]:
        """按确定顺序运行各规则，保证报告输出稳定。"""

        issues: list[Issue] = []
        issues.extend(self._detect_missing(source, target, match_result))
        issues.extend(self._detect_geometry(target, match_result))
        issues.extend(self._detect_out_of_page(target))
        issues.extend(self._detect_overlaps(source, target, match_result))
        return issues

    def _detect_missing(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """识别源元素缺失和目标文档意外新增元素。"""

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        issues: list[Issue] = []
        for region_id in result.unmatched_source_region_ids:
            region = source_regions[region_id]
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
                    metrics={"region_type": region.type.value},
                    description="目标文档缺少源文档中的图片。"
                    if is_image
                    else "目标文档缺少可匹配的源区域。",
                    detector="missing-element",
                )
            )
        for region_id in result.unmatched_target_region_ids:
            region = target_regions[region_id]
            issues.append(
                Issue(
                    id=f"p{target.page}-added-{region_id}",
                    page=target.page,
                    type=IssueType.ADDED_ELEMENT,
                    severity=Severity.LOW,
                    target_region=region_id,
                    bbox=region.bbox,
                    metrics={"region_type": region.type.value},
                    description="目标文档出现未能与源文档匹配的新增区域。",
                    detector="missing-element",
                )
            )
        return issues

    def _is_covered_by_target_text(self, source_region: Region, target: Page) -> bool:
        """判断未匹配源文本是否已被目标文本框通过多对一方式承载。"""

        return any(
            region.type in self._TEXT_TYPES
            and intersection_ratio(source_region.bbox, region.bbox)
            >= self.thresholds.merged_text_coverage_ratio
            for region in target.regions
        )

    def _detect_geometry(
        self, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """检测显著位移和字体缩小，并保留触发规则的比例。"""

        target_regions = {region.id: region for region in target.regions}
        issues: list[Issue] = []
        for diff in result.diffs:
            target_region = target_regions[diff.target_region_id]
            shift = max(abs(diff.x_shift_ratio), abs(diff.y_shift_ratio))
            if shift > self.thresholds.shifted_ratio:
                severity = (
                    Severity.HIGH
                    if shift > self.thresholds.severely_shifted_ratio
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
                        },
                        description="目标区域相对源区域发生显著位置偏移。",
                        detector="geometry",
                    )
                )

            font_change = diff.font_size_change_ratio
            if font_change is not None and font_change < self.thresholds.font_shrink_ratio:
                issues.append(
                    Issue(
                        id=f"p{target.page}-font-{diff.target_region_id}",
                        page=target.page,
                        type=IssueType.FONT_SHRINK,
                        # 字号缩小本身需要人工复核；只有同时出现裁切、越界等
                        # 可见内容损失时，才由相应规则升级为 Critical。
                        severity=Severity.HIGH,
                        source_region=diff.source_region_id,
                        target_region=diff.target_region_id,
                        bbox=target_region.bbox,
                        metrics={"font_size_change_ratio": font_change},
                        description="目标区域字号为适应版面而明显缩小。",
                        detector="typography",
                    )
                )
        return issues

    @staticmethod
    def _detect_out_of_page(target: Page) -> list[Issue]:
        """检测区域边界超出页面可见范围。"""

        issues: list[Issue] = []
        for region in target.regions:
            if (
                region.bbox.x < 0
                or region.bbox.y < 0
                or region.bbox.right > target.width
                or region.bbox.bottom > target.height
            ):
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
                        },
                        description="目标区域超出页面边界，内容可能被裁切。",
                        detector="overflow",
                    )
                )
        return issues

    def _detect_overlaps(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """只报告翻译后新增或显著加剧的区域重叠。"""

        issues: list[Issue] = []
        for first, second in combinations(target.regions, 2):
            ratio = intersection_ratio(first.bbox, second.bbox)
            if ratio <= self.thresholds.overlap_ratio:
                continue
            first_is_text = first.type in self._TEXT_TYPES
            second_is_text = second.type in self._TEXT_TYPES
            is_text_image = (
                first_is_text and second.type == ElementType.IMAGE
            ) or (second_is_text and first.type == ElementType.IMAGE)
            if not is_text_image and not (first_is_text and second_is_text):
                continue

            source_ratio = 0.0
            source_first = self._find_layout_analog(first, source, target)
            source_second = self._find_layout_analog(second, source, target)
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
                    <= self.thresholds.image_caption_area_ratio
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
            if ratio - source_ratio <= self.thresholds.overlap_increase_ratio:
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
                    target_region=first.id,
                    bbox=first.bbox,
                    metrics={
                        "overlap_ratio": ratio,
                        "source_overlap_ratio": source_ratio,
                        "overlap_increase_ratio": ratio - source_ratio,
                        "other_region": second.id,
                    },
                    description="目标文本与图片发生明显重叠。"
                    if is_text_image
                    else "目标文本区域之间发生明显重叠。",
                    detector="overlap",
                )
            )
        return issues

    def _find_layout_analog(
        self, target_region: Region, source: Page, target: Page
    ) -> Region | None:
        """独立查找同类型且版面最接近的源区域，用于比较拓扑关系。"""

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
        if not candidates:
            return None

        def layout_score(candidate: Region) -> float:
            """拓扑对照更重视位置，尺寸只用于区分同位置的多个对象。"""

            return 0.7 * position_similarity(
                candidate.bbox,
                target_region.bbox,
                max(source.width, target.width),
                max(source.height, target.height),
            ) + 0.3 * size_similarity(candidate.bbox, target_region.bbox)

        best = max(candidates, key=layout_score)
        return best if layout_score(best) >= self.thresholds.minimum_match_score else None

    @staticmethod
    def _center_inside(inner: BoundingBox, outer: BoundingBox) -> bool:
        """判断第一个 BBox 的中心是否位于第二个 BBox 内部。"""

        center_x = inner.x + inner.width / 2
        center_y = inner.y + inner.height / 2
        return (
            outer.x <= center_x <= outer.right
            and outer.y <= center_y <= outer.bottom
        )
