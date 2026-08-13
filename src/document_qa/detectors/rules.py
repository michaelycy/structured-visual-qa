"""MVP 使用的布局、缺失和字体规则检测。"""

from itertools import combinations

from document_qa.config import QAThresholds
from document_qa.matching.geometry import intersection_ratio
from document_qa.schemas import (
    ElementType,
    Issue,
    IssueType,
    Page,
    PageMatchResult,
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
        issues.extend(self._detect_overlaps(target))
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
                severity = (
                    Severity.CRITICAL
                    if font_change < self.thresholds.critical_font_shrink_ratio
                    else Severity.HIGH
                )
                issues.append(
                    Issue(
                        id=f"p{target.page}-font-{diff.target_region_id}",
                        page=target.page,
                        type=IssueType.FONT_SHRINK,
                        severity=severity,
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

    def _detect_overlaps(self, target: Page) -> list[Issue]:
        """检测独立 Region 之间具有交付风险的面积重叠。"""

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
                        "other_region": second.id,
                    },
                    description="目标文本与图片发生明显重叠。"
                    if is_text_image
                    else "目标文本区域之间发生明显重叠。",
                    detector="overlap",
                )
            )
        return issues

