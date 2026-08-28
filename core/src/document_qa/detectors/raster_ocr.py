"""对匹配的大图片候选运行 OCR，识别图片内部的局部漏译。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from document_qa.ocr import OCRLine, OCRProvider, OCRResult
from document_qa.profiles import RuleProfile, default_rule_profile
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

ImageLoader = Callable[[Page, BoundingBox], bytes]

_SCRIPT_PATTERNS = {
    "latin": re.compile(r"[A-Za-z]"),
    "cjk": re.compile(r"[\u3040-\u30ff\u3400-\u9fff]"),
    "cyrillic": re.compile(r"[\u0400-\u04ff]"),
    "arabic": re.compile(r"[\u0600-\u06ff]"),
}


@dataclass
class RasterOCRDetectionResult:
    """单页 OCR 检测结果及运行状态摘要。"""

    issues: list[Issue] = field(default_factory=list)
    candidate_count: int = 0
    processed_count: int = 0
    error: str | None = None


class RasterOCRDetector:
    """通过可注入 OCR 适配器确认大图片内仍保留的源语言文字。"""

    def __init__(
        self,
        provider: OCRProvider,
        profile: RuleProfile | None = None,
    ) -> None:
        """保存 OCR 适配器与规则配置；不在 core 初始化具体模型。"""

        self.provider = provider
        self.profile = profile or default_rule_profile()

    def detect(
        self,
        source: Page,
        target: Page,
        result: PageMatchResult,
        source_image_loader: ImageLoader,
        target_image_loader: ImageLoader,
    ) -> RasterOCRDetectionResult:
        """筛选大图候选，OCR 两侧内容并输出局部图像文字漏译问题。"""

        settings = self.profile.detector_settings_for(
            self.resolve_language(source, target)
        )
        if not settings.enabled.untranslated_raster_ocr:
            return RasterOCRDetectionResult()

        source_script = self._dominant_script(source)
        target_script = self._dominant_script(target)
        if (
            source_script in {None, "mixed"}
            or target_script in {None, "mixed"}
            or source_script == target_script
        ):
            return RasterOCRDetectionResult()

        candidates = self._candidates(source, target, result, settings.thresholds)
        detection = RasterOCRDetectionResult(candidate_count=len(candidates))
        for index, (source_region, target_region) in enumerate(candidates, start=1):
            try:
                source_ocr = self.provider.recognize(
                    source_image_loader(source, source_region.bbox)
                )
                target_ocr = self.provider.recognize(
                    target_image_loader(target, target_region.bbox)
                )
                detection.processed_count += 1
            except Exception as exc:
                # OCR 是可选增强能力；运行失败必须进入报告元数据，但不能
                # 让原有确定性流水线或第 6 页图像指纹证据一起失败。
                detection.error = type(exc).__name__
                break
            issue = self._build_issue(
                source,
                target,
                source_region,
                target_region,
                source_ocr,
                target_ocr,
                source_script,
                target_script,
                index,
                settings,
            )
            if issue is not None:
                detection.issues.append(issue)
        return detection

    def _candidates(self, source, target, result, thresholds):
        """返回位置尺寸稳定、面积足够且内容已变化的大图片配对。"""

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        source_blocks = {block.id: block for block in source.blocks}
        target_blocks = {block.id: block for block in target.blocks}
        page_area = target.width * target.height
        candidates: list[tuple[Region, Region]] = []
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
                or target_region.bbox.area / page_area
                < thresholds.untranslated_raster_ocr_min_area_ratio
            ):
                continue
            # 完全相同的图像已由 P1 指纹规则处理；P2 专门覆盖局部改动后
            # 仍残留源语言文字的大图，避免同一区域重复出两条 Issue。
            source_hashes = self._image_hashes(source_region, source_blocks)
            target_hashes = self._image_hashes(target_region, target_blocks)
            if source_hashes and source_hashes == target_hashes:
                continue
            candidates.append((source_region, target_region))
        candidates.sort(key=lambda pair: -pair[1].bbox.area)
        return candidates[: thresholds.untranslated_raster_ocr_max_candidates]

    def _build_issue(
        self,
        source: Page,
        target: Page,
        source_region: Region,
        target_region: Region,
        source_ocr: OCRResult,
        target_ocr: OCRResult,
        source_script: str,
        target_script: str,
        index: int,
        settings,
    ) -> Issue | None:
        """根据 OCR 脚本残留比例生成一条可定位问题。"""

        threshold = settings.thresholds
        source_lines = self._trusted_lines(source_ocr, threshold)
        target_lines = self._trusted_lines(target_ocr, threshold)
        source_chars = self._script_count(source_lines, source_script)
        target_source_chars = self._script_count(target_lines, source_script)
        target_script_chars = self._script_count(target_lines, target_script)
        total_target_chars = target_source_chars + target_script_chars
        source_ratio = (
            target_source_chars / total_target_chars if total_target_chars else 0.0
        )
        if (
            source_chars < threshold.untranslated_raster_ocr_min_source_chars
            or target_source_chars
            < threshold.untranslated_raster_ocr_min_target_chars
            or source_ratio < threshold.untranslated_raster_ocr_source_ratio
        ):
            return None

        residue_lines = [
            line
            for line in target_lines
            if _SCRIPT_PATTERNS[source_script].search(line.text)
        ]
        bbox = self._map_lines_to_page(
            residue_lines,
            target_ocr,
            self._expanded_bbox(
                target_region.bbox,
                target.width,
                target.height,
                threshold.untranslated_raster_ocr_padding_points,
            ),
        )
        confidence = mean(line.confidence for line in residue_lines)
        default_severity = (
            Severity.HIGH
            if target_source_chars
            >= threshold.untranslated_raster_ocr_high_source_chars
            else threshold.band_severity(
                threshold.untranslated_bands, source_ratio, Severity.MEDIUM
            )
        )
        severity = settings.severity_for(
            IssueType.UNTRANSLATED_RASTER, default_severity
        )
        snippet = " ".join(line.text.strip() for line in residue_lines if line.text)
        return Issue(
            id=f"p{target.page}-untranslated-raster-ocr-{index}",
            page=target.page,
            type=IssueType.UNTRANSLATED_RASTER,
            severity=severity,
            source_region=source_region.id,
            target_region=target_region.id,
            bbox=bbox,
            metrics={
                "detection_mode": "ocr_partial",
                "ocr_status": "confirmed",
                "ocr_provider": self.provider.provider_name,
                "ocr_model": self.provider.model_fingerprint,
                "source_script": source_script,
                "target_script": target_script,
                "source_ocr_script_chars": source_chars,
                "target_ocr_source_script_chars": target_source_chars,
                "target_ocr_target_script_chars": target_script_chars,
                "ocr_high_source_chars_threshold": (
                    threshold.untranslated_raster_ocr_high_source_chars
                ),
                "target_source_script_ratio": round(source_ratio, 4),
                "ocr_confidence": round(confidence, 4),
                "ocr_line_count": len(target_lines),
                "ocr_residue_line_count": len(residue_lines),
                "ocr_text_snippet": snippet[:160],
                "candidate_bbox_area_ratio": round(
                    target_region.bbox.area / (target.width * target.height), 4
                ),
            },
            description=(
                "目标图片内部仍识别到较多源语言文字，疑似图片标签仅部分翻译；"
                "请按标注区域复核。"
            ),
            detector="content-untranslated-raster-ocr",
        )

    @staticmethod
    def _trusted_lines(result: OCRResult, thresholds) -> list[OCRLine]:
        """过滤低置信度与纯空白 OCR 行。"""

        return [
            line
            for line in result.lines
            if line.text.strip()
            and line.confidence >= thresholds.untranslated_raster_ocr_min_confidence
        ]

    @staticmethod
    def _script_count(lines: list[OCRLine], script: str) -> int:
        """统计一组 OCR 行中指定脚本的字符数。"""

        return sum(len(_SCRIPT_PATTERNS[script].findall(line.text)) for line in lines)

    @staticmethod
    def _map_lines_to_page(
        lines: list[OCRLine], result: OCRResult, region_bbox: BoundingBox
    ) -> BoundingBox:
        """把 OCR 图片像素坐标中的文字框映射回 PDF 页面坐标。"""

        if not lines:
            return region_bbox
        x0 = min(line.bbox.x for line in lines)
        y0 = min(line.bbox.y for line in lines)
        x1 = max(line.bbox.right for line in lines)
        y1 = max(line.bbox.bottom for line in lines)
        scale_x = region_bbox.width / result.image_width
        scale_y = region_bbox.height / result.image_height
        return BoundingBox(
            x=region_bbox.x + x0 * scale_x,
            y=region_bbox.y + y0 * scale_y,
            width=max((x1 - x0) * scale_x, 0.01),
            height=max((y1 - y0) * scale_y, 0.01),
        )

    @staticmethod
    def _expanded_bbox(
        bbox: BoundingBox,
        page_width: float,
        page_height: float,
        padding: float,
    ) -> BoundingBox:
        """返回与 Renderer 裁剪一致、限制在页面内的扩展区域。"""

        x0 = max(0.0, bbox.x - padding)
        y0 = max(0.0, bbox.y - padding)
        x1 = min(page_width, bbox.right + padding)
        y1 = min(page_height, bbox.bottom + padding)
        return BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)

    @staticmethod
    def _image_hashes(region: Region, blocks_by_id: dict) -> tuple[str, ...]:
        """读取 Region 子图片的内容摘要。"""

        values = []
        for block_id in region.children:
            block = blocks_by_id.get(block_id)
            metadata = getattr(block, "metadata", None)
            digest = metadata.get("content_sha256") if metadata else None
            if isinstance(digest, str) and digest:
                values.append(digest)
        return tuple(values)

    @staticmethod
    def _dominant_script(page: Page) -> str | None:
        """按页面可提取文字的字符总量判断主导脚本。"""

        counts = {
            name: sum(
                len(pattern.findall(region.content.text or ""))
                for region in page.regions
                if region.content and region.content.text
            )
            for name, pattern in _SCRIPT_PATTERNS.items()
        }
        positive = sorted(
            ((name, count) for name, count in counts.items() if count),
            key=lambda item: (-item[1], item[0]),
        )
        if not positive:
            return None
        if len(positive) > 1 and positive[0][1] == positive[1][1]:
            return "mixed"
        return positive[0][0]

    def resolve_language(self, source: Page, target: Page) -> str:
        """返回 Profile 语言覆盖所使用的源脚本-目标脚本标识。"""

        source_script = self._dominant_script(source)
        target_script = self._dominant_script(target)
        if source_script and target_script:
            return f"{source_script}-{target_script}"
        return self.profile.language
