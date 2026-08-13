import tempfile
import unittest
from pathlib import Path

import pymupdf

from document_qa.parsers import PyMuPDFParser
from document_qa.pipeline import DocumentQAPipeline
from document_qa.reporting import JSONReporter
from document_qa.schemas import QAReport, QAStatus


def create_pdf(path: Path, *, pages: int = 1, x_shift: float = 0) -> None:
    """生成无外部资源的测试 PDF，避免仓库保存真实文档样本。"""

    document = pymupdf.open()
    for page_number in range(pages):
        page = document.new_page(width=300, height=400)
        page.insert_text(
            (40 + x_shift, 60),
            f"Structured QA page {page_number + 1}",
            fontsize=14,
        )
        page.insert_textbox(
            pymupdf.Rect(40 + x_shift, 100, 250 + x_shift, 180),
            "Translated document layout verification.",
            fontsize=11,
        )
    document.save(path)
    document.close()


class PyMuPDFPipelineTests(unittest.TestCase):
    """验证真实 PyMuPDF 文件的解析、渲染和完整流水线。"""

    def test_parser_extracts_pages_and_text_blocks(self) -> None:
        """解析器应把测试 PDF 转换为 Page 和文本 Block。"""

        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "source.pdf"
            create_pdf(pdf_path)

            document = PyMuPDFParser().parse(pdf_path)

            self.assertEqual(len(document.pages), 1)
            self.assertGreater(len(document.pages[0].blocks), 0)

    def test_pipeline_writes_schema_valid_report_and_renders_pages(self) -> None:
        """端到端结果应可重新校验，并生成源/目标页面图。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pdf"
            target_path = root / "target.pdf"
            create_pdf(source_path)
            create_pdf(target_path, x_shift=3)

            report = DocumentQAPipeline().compare(
                source_path, target_path, render_dir=root / "rendered"
            )
            report_path = JSONReporter().write(report, root / "report.json")
            validated = QAReport.model_validate_json(report_path.read_text("utf-8"))

            self.assertEqual(validated.summary.pages, 1)
            self.assertTrue((root / "rendered/source/page-0001.png").is_file())
            self.assertTrue((root / "rendered/target/page-0001.png").is_file())

    def test_missing_page_forces_document_failure(self) -> None:
        """目标 PDF 缺少整页时，文档状态必须为 FAIL。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.pdf"
            target_path = root / "target.pdf"
            create_pdf(source_path, pages=2)
            create_pdf(target_path, pages=1)

            report = DocumentQAPipeline().compare(source_path, target_path)

            self.assertEqual(report.status, QAStatus.FAIL)
            self.assertEqual(report.summary.failed_pages, 1)


if __name__ == "__main__":
    unittest.main()

