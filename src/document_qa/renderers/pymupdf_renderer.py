"""使用 PyMuPDF 渲染 PDF 页面。"""

from pathlib import Path

import pymupdf

from document_qa.parsers.base import DocumentParsingError


class PyMuPDFRenderer:
    """将 PDF 页面渲染为按页编号的 PNG 文件。"""

    def __init__(self, *, dpi: int = 144, max_pages: int = 500) -> None:
        """初始化渲染分辨率和页数安全上限。"""

        if dpi <= 0:
            raise ValueError("dpi 必须大于 0")
        self.dpi = dpi
        self.max_pages = max_pages

    def render(self, pdf_path: Path, output_dir: Path) -> list[Path]:
        """渲染全部页面，输出文件名只使用页码以避免路径注入。"""

        source_path = pdf_path.expanduser().resolve()
        if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
            raise DocumentParsingError(f"无效 PDF 路径: {source_path}")

        safe_output_dir = output_dir.expanduser().resolve()
        safe_output_dir.mkdir(parents=True, exist_ok=True)
        rendered_paths: list[Path] = []

        try:
            with pymupdf.open(source_path) as pdf:
                if pdf.page_count > self.max_pages:
                    raise DocumentParsingError(
                        f"PDF 页数 {pdf.page_count} 超过限制 {self.max_pages}"
                    )
                for page_index, page in enumerate(pdf):
                    # DPI 直接交给 MuPDF 处理，避免自行换算矩阵造成尺寸偏差。
                    pixmap = page.get_pixmap(dpi=self.dpi, alpha=False)
                    output_path = safe_output_dir / f"page-{page_index + 1:04d}.png"
                    pixmap.save(output_path)
                    rendered_paths.append(output_path)
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"PDF 渲染失败: {exc}") from exc

        return rendered_paths

