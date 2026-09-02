"""使用 PyMuPDF 渲染 PDF 页面。"""

from pathlib import Path

import pymupdf

from document_qa.parsers.base import DocumentParsingError
from document_qa.schemas import BoundingBox


class PyMuPDFRenderer:
    """将 PDF 页面渲染为按页编号的 PNG 文件。"""

    def __init__(self, *, dpi: int = 144, max_pages: int = 500) -> None:
        """初始化渲染分辨率和页数安全上限。"""

        if dpi <= 0:
            raise ValueError("dpi 必须大于 0")
        self.dpi = dpi
        self.max_pages = max_pages
        # 整页像素缓存（验证层采样用）：键 (路径, 页码, dpi)，容量按
        # LRU 淘汰——96 dpi 的 A4 页约 2.3 MB，4 页足以覆盖逐页验证
        # 的访问模式，又不让长文档占满内存。
        self._pixel_cache: dict[tuple[str, int, int], tuple[int, int, bytes]] = {}
        self._pixel_cache_order: list[tuple[str, int, int]] = []
        self._pixel_cache_capacity = 4

    def page_pixels(
        self,
        pdf_path: Path,
        *,
        page: int,
        dpi: int,
        password: str | None = None,
    ) -> tuple[int, int, bytes]:
        """渲染整页为 RGB 像素并缓存，返回 (宽, 高, RGB 字节流)。

        供渲染验证层做像素采样（T38）； pymupdf 对象不越过本边界，
        调用方只拿到纯 Python 数据。缓存与 dpi 相关，密码仅参与打开。
        """

        if page < 1 or dpi <= 0:
            raise ValueError("页码与 dpi 必须为正数")
        source_path = pdf_path.expanduser().resolve()
        cache_key = (str(source_path), page, dpi)
        cached = self._pixel_cache.get(cache_key)
        if cached is not None:
            return cached
        if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
            raise DocumentParsingError(f"无效 PDF 路径: {source_path}")
        try:
            with pymupdf.open(source_path) as pdf:
                if pdf.needs_pass:
                    if password is None:
                        raise DocumentParsingError("渲染需要提供打开密码")
                    if not pdf.authenticate(password):
                        raise DocumentParsingError("PDF 打开密码错误")
                if page > pdf.page_count:
                    raise DocumentParsingError(f"PDF 不存在第 {page} 页")
                pix = pdf[page - 1].get_pixmap(
                    matrix=pymupdf.Matrix(dpi / 72, dpi / 72),
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                pixels = (pix.width, pix.height, bytes(pix.samples))
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"页面渲染失败: {type(exc).__name__}") from exc
        if cache_key in self._pixel_cache_order:
            self._pixel_cache_order.remove(cache_key)
        self._pixel_cache_order.append(cache_key)
        self._pixel_cache[cache_key] = pixels
        while len(self._pixel_cache_order) > self._pixel_cache_capacity:
            evicted = self._pixel_cache_order.pop(0)
            self._pixel_cache.pop(evicted, None)
        return pixels

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

    def render_crop_png(
        self,
        pdf_path: Path,
        *,
        page: int,
        bbox: BoundingBox,
        dpi: int,
        padding_points: float = 0.0,
        password: str | None = None,
    ) -> bytes:
        """把一个 PDF 页面区域渲染为内存 PNG，供可选 OCR 使用。

        返回值仅在当前检测调用中传递，不写入 Block metadata、报告或磁盘。
        """

        source_path = pdf_path.expanduser().resolve()
        if not source_path.is_file() or source_path.suffix.lower() != ".pdf":
            raise DocumentParsingError(f"无效 PDF 路径: {source_path}")
        if page < 1 or dpi <= 0 or padding_points < 0:
            raise ValueError("OCR 裁剪页码、DPI 与边距必须有效")

        try:
            with pymupdf.open(source_path) as pdf:
                if pdf.needs_pass:
                    if password is None:
                        raise DocumentParsingError(
                            "PDF 受打开密码保护，OCR 渲染需要提供密码"
                        )
                    if not pdf.authenticate(password):
                        raise DocumentParsingError("PDF 打开密码错误")
                if page > pdf.page_count:
                    raise DocumentParsingError(f"PDF 不存在第 {page} 页")
                pdf_page = pdf[page - 1]
                page_rect = pdf_page.rect
                clip = pymupdf.Rect(
                    bbox.x - padding_points,
                    bbox.y - padding_points,
                    bbox.right + padding_points,
                    bbox.bottom + padding_points,
                ) & page_rect
                if clip.is_empty or clip.width <= 0 or clip.height <= 0:
                    raise DocumentParsingError("OCR 候选区域不在页面可见范围内")
                pixmap = pdf_page.get_pixmap(dpi=dpi, alpha=False, clip=clip)
                return pixmap.tobytes("png")
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"OCR 区域渲染失败: {exc}") from exc
