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

    def render(
        self,
        pdf_path: Path,
        output_dir: Path,
        pages: set[int] | None = None,
        password: str | None = None,
    ) -> list[Path]:
        """渲染页面；pages 为 None 时渲染全部，否则只渲染指定页码集合。

        password 与解析侧一致：仅打开密码（user password）文档需要，
        权限密码文档 MuPDF 自动解密。渲染红框对比图需要同样的解密能力。
        """

        source_path = pdf_path.expanduser().resolve()
        if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
            raise DocumentParsingError(f"无效 PDF 路径: {source_path}")

        safe_output_dir = output_dir.expanduser().resolve()
        safe_output_dir.mkdir(parents=True, exist_ok=True)
        rendered_paths: list[Path] = []

        try:
            with pymupdf.open(source_path) as pdf:
                if pdf.needs_pass:
                    if password is None:
                        raise DocumentParsingError(
                            "PDF 受打开密码保护，渲染页面需要提供密码"
                        )
                    if not pdf.authenticate(password):
                        raise DocumentParsingError("PDF 打开密码错误")
                if pdf.page_count > self.max_pages:
                    raise DocumentParsingError(
                        f"PDF 页数 {pdf.page_count} 超过限制 {self.max_pages}"
                    )
                for page_index, page in enumerate(pdf):
                    page_number = page_index + 1
                    if pages is not None and page_number not in pages:
                        continue
                    # DPI 直接交给 MuPDF 处理，避免自行换算矩阵造成尺寸偏差。
                    pixmap = page.get_pixmap(dpi=self.dpi, alpha=False)
                    output_path = safe_output_dir / f"page-{page_number:04d}.png"
                    pixmap.save(output_path)
                    rendered_paths.append(output_path)
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"PDF 渲染失败: {exc}") from exc

        return rendered_paths

