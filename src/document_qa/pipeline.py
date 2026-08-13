"""Structured Visual QA 端到端应用流水线。"""

from collections import Counter
from pathlib import Path

from document_qa.detectors import RuleDetector
from document_qa.grouping import RegionGrouper
from document_qa.matching import RegionMatcher
from document_qa.parsers import PyMuPDFParser
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


class DocumentQAPipeline:
    """协调解析、分组、匹配、检测、评分和可选页面渲染。"""

    def __init__(
        self,
        *,
        parser: PyMuPDFParser | None = None,
        renderer: PyMuPDFRenderer | None = None,
        grouper: RegionGrouper | None = None,
        matcher: RegionMatcher | None = None,
        detector: RuleDetector | None = None,
        scorer: QAScorer | None = None,
    ) -> None:
        """支持依赖注入，便于测试和后续替换 PDF 引擎。"""

        self.parser = parser or PyMuPDFParser()
        self.renderer = renderer or PyMuPDFRenderer()
        self.grouper = grouper or RegionGrouper()
        self.matcher = matcher or RegionMatcher()
        self.detector = detector or RuleDetector()
        self.scorer = scorer or QAScorer()

    def compare(
        self,
        source_path: Path,
        target_path: Path,
        *,
        render_dir: Path | None = None,
    ) -> QAReport:
        """比较两个 PDF，并返回经过 Schema 校验的完整 QA 报告。"""

        source = self._group_document(self.parser.parse(source_path))
        target = self._group_document(self.parser.parse(target_path))

        if render_dir is not None:
            # 使用固定子目录隔离源文档与目标文档页面，避免同名文件互相覆盖。
            self.renderer.render(source_path, render_dir / "source")
            self.renderer.render(target_path, render_dir / "target")

        source_pages = {page.page: page for page in source.pages}
        target_pages = {page.page: page for page in target.pages}
        page_numbers = sorted(source_pages.keys() | target_pages.keys())
        page_results = [
            self._compare_page(
                page_number,
                source_pages.get(page_number),
                target_pages.get(page_number),
            )
            for page_number in page_numbers
        ]
        return self._build_report(source, target, page_results)

    def _group_document(self, document: Document) -> Document:
        """为文档中的每一页建立 Region，保留原始 Block 供追溯。"""

        pages = [self.grouper.group_page(page) for page in document.pages]
        return document.model_copy(update={"pages": pages})

    def _compare_page(
        self, page_number: int, source: Page | None, target: Page | None
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

        match_result = self.matcher.match_page(source, target)
        issues = self.detector.detect(source, target, match_result)
        score, status = self.scorer.score(issues)
        return PageQAResult(
            page=page_number,
            score=score,
            status=status,
            matches=match_result.matches,
            diffs=match_result.diffs,
            issues=issues,
        )

    @staticmethod
    def _build_report(
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
        )
        return QAReport(
            source_document_id=source.document_id,
            target_document_id=target.document_id,
            document_score=document_score,
            status=status,
            summary=summary,
            pages=page_results,
        )

