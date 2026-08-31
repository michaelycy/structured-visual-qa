"""Structured Visual QA 端到端应用流水线。"""

from collections import Counter
from pathlib import Path
from typing import Literal

from document_qa.detectors import ContentDetector, RuleDetector
from document_qa.detectors.glossary import GlossaryDetector
from document_qa.detectors.raster_ocr import RasterOCRDetector
from document_qa.grouping import RegionGrouper
from document_qa.matching import LogicalRegionComposer, PageAligner, RegionMatcher
from document_qa.ocr import OCRProvider
from document_qa.parsers import PyMuPDFParser
from document_qa.glossary import Glossary
from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.problem_groups import count_problem_groups
from document_qa.renderers import PyMuPDFRenderer
from document_qa.schemas import (
    Document,
    Issue,
    IssueType,
    Page,
    PageQAResult,
    QAReport,
    QAStatus,
    ReportSummary,
    Severity,
)
from document_qa.scoring import QAScorer

RenderScope = Literal["all", "issues"]


class DocumentQAPipeline:
    """协调解析、分组、页对齐、匹配、检测、评分和可选页面渲染。"""

    def __init__(
        self,
        *,
        profile: RuleProfile | None = None,
        parser: PyMuPDFParser | None = None,
        renderer: PyMuPDFRenderer | None = None,
        grouper: RegionGrouper | None = None,
        logical_region_composer: LogicalRegionComposer | None = None,
        page_aligner: PageAligner | None = None,
        matcher: RegionMatcher | None = None,
        detector: RuleDetector | None = None,
        content_detector: ContentDetector | None = None,
        scorer: QAScorer | None = None,
        glossary: Glossary | None = None,
        ocr_provider: OCRProvider | None = None,
    ) -> None:
        """支持注入 Profile 与组件，便于界面配置、测试和替换 PDF 引擎。"""

        self.profile = profile or default_rule_profile()
        # 背景识别阈值来自同一 Profile：隐形文字检测的背景判断与
        # 检测阈值随一次配置修改贯穿全流程。
        self.parser = parser or PyMuPDFParser(background=self.profile.background)
        self.renderer = renderer or PyMuPDFRenderer()
        self.grouper = grouper or RegionGrouper(self.profile)
        self.logical_region_composer = (
            logical_region_composer or LogicalRegionComposer(self.profile)
        )
        # 默认组件必须共享同一个 Profile，确保界面中一次配置修改贯穿全流程。
        self.page_aligner = page_aligner or PageAligner(self.profile)
        self.matcher = matcher or RegionMatcher(self.profile)
        self.detector = detector or RuleDetector(self.profile)
        self.content_detector = content_detector or ContentDetector(self.profile)
        self.scorer = scorer or QAScorer(self.profile)
        # 术语库可选；缺省不启用术语检测（行为与历史版本一致）。
        self.glossary_detector = GlossaryDetector(glossary) if glossary else None
        self.raster_ocr_detector = (
            RasterOCRDetector(ocr_provider, self.profile) if ocr_provider else None
        )
        self._ocr_run: dict[str, object] | None = None

    def compare(
        self,
        source_path: Path,
        target_path: Path,
        *,
        render_dir: Path | None = None,
        render_scope: RenderScope = "all",
        source_password: str | None = None,
        target_password: str | None = None,
    ) -> QAReport:
        """比较两个 PDF，并返回经过 Schema 校验的完整 QA 报告。

        source_password / target_password 用于带打开密码的 PDF，
        只在内存中传递给解析与渲染，绝不写入报告或历史产物。
        """

        source = self._group_document(
            self.parser.parse(source_path, password=source_password)
        )
        target = self._group_document(
            self.parser.parse(target_path, password=target_password)
        )

        source_pages = {page.page: page for page in source.pages}
        target_pages = {page.page: page for page in target.pages}
        alignment = self.page_aligner.align(source, target)

        # (报告页码, 源页面, 目标页面)；跨页对齐时源/目标页码可以不同。
        entries: list[tuple[int, Page | None, Page | None]] = []
        for source_number, target_number in alignment.pairs:
            entries.append(
                (source_number, source_pages[source_number], target_pages[target_number])
            )
        for number in alignment.missing_source_pages:
            entries.append((number, source_pages[number], None))
        for number in alignment.extra_target_pages:
            entries.append((number, None, target_pages[number]))
        entries.sort(key=lambda entry: entry[0])

        if self.raster_ocr_detector is not None:
            self._ocr_run = {
                "status": "ready",
                "provider": self.raster_ocr_detector.provider.provider_name,
                "model": self.raster_ocr_detector.provider.model_fingerprint,
                "candidate_count": 0,
                "processed_count": 0,
            }
        else:
            self._ocr_run = None

        page_results = [
            self._compare_page(
                number,
                source_page,
                target_page,
                source_path=source_path,
                target_path=target_path,
                source_password=source_password,
                target_password=target_password,
            )
            for number, source_page, target_page in entries
        ]
        report = self._build_report(source, target, page_results)

        if render_dir is not None:
            self._render_pages(
                render_dir,
                render_scope,
                source_path,
                target_path,
                entries,
                page_results,
                source_password=source_password,
                target_password=target_password,
            )
        return report

    def _render_pages(
        self,
        render_dir: Path,
        render_scope: RenderScope,
        source_path: Path,
        target_path: Path,
        entries: list[tuple[int, Page | None, Page | None]],
        page_results: list[PageQAResult],
        *,
        source_password: str | None = None,
        target_password: str | None = None,
    ) -> None:
        """使用固定子目录隔离源/目标页面，按范围渲染。

        render_scope 为 "issues" 时只渲染状态非 PASS 的页面，两侧文档
        的对应页码会分别加入渲染集合，避免大文档全量渲染。
        """

        source_render_pages: set[int] = set()
        target_render_pages: set[int] = set()
        for (_, source_page, target_page), result in zip(entries, page_results, strict=True):
            # "issues" 范围渲染两类页面：判定非 PASS 的，以及带 Issue 但
            # 总分仍达标的（如归一化噪声只产生少量 MEDIUM 偏移、页面 96
            # 分 PASS 的 PPT）——后者同样需要对比图供人工复核。
            include = (
                render_scope == "all"
                or result.status != QAStatus.PASS
                or bool(result.issues)
            )
            if include and source_page is not None:
                source_render_pages.add(source_page.page)
            if include and target_page is not None:
                target_render_pages.add(target_page.page)
        if source_render_pages:
            self.renderer.render(
                source_path,
                render_dir / "source",
                source_render_pages,
                password=source_password,
            )
        if target_render_pages:
            self.renderer.render(
                target_path,
                render_dir / "target",
                target_render_pages,
                password=target_password,
            )

    def _is_text_vectorized(self, source: Page, target: Page) -> bool:
        """判断目标页文字是否被矢量化（转曲）。

        用总文本字符数而非区域数判断：区域数受分组粒度影响（多行
        文本可能合成一个 Region），字符数是文本层是否存在的直接
        证据。源页有足量字符而目标页字符骤降（阈值见 RuleProfile）
        说明目标文字被转成矢量路径——内容仍在页面上，但文本层提取
        不到，内容级检测（数字/漏译/术语/文本缺失）会全部假阳性。
        """

        thresholds = self.profile.detectors.thresholds
        source_chars = sum(
            len(r.content.text) for r in source.regions if r.content and r.content.text
        )
        target_chars = sum(
            len(r.content.text) for r in target.regions if r.content and r.content.text
        )
        if source_chars < thresholds.vectorized_min_source_chars:
            return False
        return target_chars <= source_chars * thresholds.vectorized_max_target_ratio

    def _group_document(self, document: Document) -> Document:
        """为文档中的每一页建立 Region，保留原始 Block 供追溯。"""

        pages = [self.grouper.group_page(page) for page in document.pages]
        return document.model_copy(update={"pages": pages})

    def _compare_page(
        self,
        page_number: int,
        source: Page | None,
        target: Page | None,
        *,
        source_path: Path | None = None,
        target_path: Path | None = None,
        source_password: str | None = None,
        target_password: str | None = None,
    ) -> PageQAResult:
        """处理正常页面、源页面缺失和目标额外页面三种情况。"""

        if source is None and target is not None:
            issue = Issue(
                id=f"p{page_number}-extra-page",
                page=page_number,
                type=IssueType.ADDED_ELEMENT,
                severity=Severity.HIGH,
                description="目标文档包含源文档中不存在的额外页面。",
                metrics={"target_region_count": len(target.regions)},
                detector="page-alignment",
            )
            score, status = self.scorer.score([issue])
            return PageQAResult(
                page=page_number, score=score, status=status, issues=[issue]
            )

        if source is not None and target is None:
            issue = Issue(
                id=f"p{page_number}-missing-page",
                page=page_number,
                type=IssueType.PAGE_MISSING,
                severity=Severity.CRITICAL,
                description="目标文档缺少源文档中的完整页面。",
                metrics={"source_region_count": len(source.regions)},
                detector="page-alignment",
            )
            score, status = self.scorer.score([issue])
            return PageQAResult(
                page=page_number, score=score, status=status, issues=[issue]
            )

        if source is None or target is None:
            raise RuntimeError("页面对齐进入不可达状态")

        # 原始 Region 保留解析器结构供追溯；匹配视图将视觉连续文本规范化，
        # 使两侧不同的 M↔N Block/Region 粒度都落到逻辑 1↔1 比较。
        source_match_page, target_match_page = (
            self.logical_region_composer.compose_pair(source, target)
        )
        match_result = self.matcher.match_page(source_match_page, target_match_page)
        issues = self.detector.detect(
            source_match_page, target_match_page, match_result
        )
        if self._is_text_vectorized(source_match_page, target_match_page):
            # 目标文字已矢量化（转曲）：文本层为空，内容级检测与
            # 文本缺失判定必然假阳性（内容其实在，只是提取不到）。
            # 抑制这些检测并显式提示，避免误导验收人。
            issues = [
                issue
                for issue in issues
                if issue.type != IssueType.MISSING_ELEMENT
            ]
            issues.append(
                Issue(
                    id=f"p{target.page}-vectorized",
                    page=target.page,
                    type=IssueType.TEXT_VECTORIZED,
                    severity=Severity.INFO,
                    description=(
                        "目标页面文字已矢量化（转曲），无法进行内容级质检"
                        "（数字一致性、漏译、术语），布局与图片检测照常。"
                    ),
                    metrics={
                        "source_text_chars": sum(
                            len(r.content.text)
                            for r in source_match_page.regions
                            if r.content and r.content.text
                        ),
                        "target_text_chars": sum(
                            len(r.content.text)
                            for r in target_match_page.regions
                            if r.content and r.content.text
                        ),
                    },
                    detector="pipeline",
                )
            )
        else:
            # 内容级检测（数字/漏译）复用同一匹配结果，位于布局规则之后。
            issues.extend(
                self.content_detector.detect(
                    source_match_page, target_match_page, match_result
                )
            )
            # 术语合规检测同样复用匹配结果；未配置术语库时为空。
            if self.glossary_detector is not None:
                issues.extend(
                    self.glossary_detector.detect(
                        source_match_page, target_match_page, match_result
                    )
                )
            if self.raster_ocr_detector is not None:
                if source_path is None or target_path is None:
                    raise RuntimeError("OCR 检测需要源文档与目标文档路径")
                thresholds = self.profile.detector_settings_for(
                    self.raster_ocr_detector.resolve_language(
                        source_match_page, target_match_page
                    )
                ).thresholds
                ocr_result = self.raster_ocr_detector.detect(
                    source_match_page,
                    target_match_page,
                    match_result,
                    lambda page, bbox: self.renderer.render_crop_png(
                        source_path,
                        page=page.page,
                        bbox=bbox,
                        dpi=thresholds.untranslated_raster_ocr_dpi,
                        padding_points=thresholds.untranslated_raster_ocr_padding_points,
                        password=source_password,
                    ),
                    lambda page, bbox: self.renderer.render_crop_png(
                        target_path,
                        page=page.page,
                        bbox=bbox,
                        dpi=thresholds.untranslated_raster_ocr_dpi,
                        padding_points=thresholds.untranslated_raster_ocr_padding_points,
                        password=target_password,
                    ),
                )
                issues.extend(ocr_result.issues)
                if self._ocr_run is not None:
                    self._ocr_run["candidate_count"] = int(
                        self._ocr_run["candidate_count"]
                    ) + ocr_result.candidate_count
                    self._ocr_run["processed_count"] = int(
                        self._ocr_run["processed_count"]
                    ) + ocr_result.processed_count
                    if ocr_result.error:
                        self._ocr_run["status"] = "error"
                        self._ocr_run["error"] = ocr_result.error
        score, status = self.scorer.score(issues)
        return PageQAResult(
            page=page_number,
            score=score,
            status=status,
            matches=match_result.matches,
            diffs=match_result.diffs,
            issues=issues,
        )

    def _build_report(
        self,
        source: Document,
        target: Document,
        page_results: list[PageQAResult],
    ) -> QAReport:
        """汇总页面状态、平均分和各严重度数量。"""

        document_score = (
            sum(page.score for page in page_results) / len(page_results)
            if page_results
            else 100.0
        )
        statuses = {page.status for page in page_results}
        if QAStatus.FAIL in statuses:
            status = QAStatus.FAIL
        elif QAStatus.REVIEW in statuses:
            status = QAStatus.REVIEW
        else:
            status = QAStatus.PASS

        issue_counts = Counter(
            issue.severity.value
            for page in page_results
            for issue in page.issues
        )
        summary = ReportSummary(
            pages=len(page_results),
            passed_pages=sum(page.status == QAStatus.PASS for page in page_results),
            review_pages=sum(
                page.status == QAStatus.REVIEW for page in page_results
            ),
            failed_pages=sum(page.status == QAStatus.FAIL for page in page_results),
            issue_counts={
                severity.value: issue_counts.get(severity.value, 0)
                for severity in Severity
            },
            problem_total=count_problem_groups(page_results),
        )
        if self._ocr_run is not None and self._ocr_run.get("status") == "ready":
            self._ocr_run["status"] = "completed"
        metadata = {"ocr": self._ocr_run} if self._ocr_run is not None else {}
        return QAReport(
            source_document_id=source.document_id,
            target_document_id=target.document_id,
            rule_profile_reference=self.profile.reference,
            rule_profile_snapshot=self.profile,
            document_score=document_score,
            status=status,
            summary=summary,
            pages=page_results,
            metadata=metadata,
        )
