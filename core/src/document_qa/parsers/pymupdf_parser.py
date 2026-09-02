"""使用 PyMuPDF 将 PDF 转换为统一文档模型。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import pymupdf

from document_qa.parsers.base import DocumentParsingError
from document_qa.profiles import BackgroundSettings
from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    Document,
    ElementType,
    Page,
    TextStyle,
)


class PyMuPDFParser:
    """提取 PDF 页面中的文本 Span、图片、坐标和基础样式。"""

    def __init__(
        self,
        *,
        max_file_size: int = 100 * 1024 * 1024,
        max_pages: int = 500,
        background: BackgroundSettings | None = None,
    ) -> None:
        """设置输入限制与背景识别阈值（缺省使用内置 Profile 默认值）。"""

        self.max_file_size = max_file_size
        self.max_pages = max_pages
        self.background = background or BackgroundSettings()

    def parse(
        self,
        path: Path,
        document_id: str | None = None,
        password: str | None = None,
    ) -> Document:
        """解析 PDF，并确保对外结果不包含任何 PyMuPDF 运行时对象。

        password 用于带打开密码（user password）的 PDF；仅权限密码
        （owner password）的 PDF 由 MuPDF 用空用户密码自动解密，
        无需传密码。密码只参与本次解密，不写入任何输出。
        """

        safe_path = self._validate_path(path)
        resolved_document_id = document_id or self._hash_file(safe_path)

        try:
            with pymupdf.open(safe_path) as pdf:
                if pdf.needs_pass:
                    # 区分"未提供密码"与"密码错误"：前者引导补输入，
                    # 后者明确是密码不对而不是文档损坏。
                    if password is None:
                        raise DocumentParsingError(
                            "PDF 受打开密码保护，需要提供密码后才能比较"
                        )
                    if not pdf.authenticate(password):
                        raise DocumentParsingError("PDF 打开密码错误")
                if pdf.page_count > self.max_pages:
                    raise DocumentParsingError(
                        f"PDF 页数 {pdf.page_count} 超过限制 {self.max_pages}"
                    )
                pages = [
                    self._parse_page(pdf_page, resolved_document_id)
                    for pdf_page in pdf
                ]
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"PDF 解析失败: {exc}") from exc

        return Document(
            document_id=resolved_document_id,
            source_path=str(safe_path),
            pages=pages,
            metadata={"parser": "pymupdf", "page_count": len(pages)},
        )

    def extract_image_block(
        self,
        path: Path,
        *,
        page: int,
        block_index: int,
        password: str | None = None,
    ) -> tuple[bytes, str]:
        """提取指定 PDF 图片 Block 的内嵌数据及媒体类型。

        返回值仅包含可序列化字节和 MIME 类型，不向调用方泄漏 PyMuPDF
        运行时对象。浏览器原生不支持的图片编码会无损解码为 PNG。
        """

        safe_path = self._validate_path(path)
        if page < 1:
            raise DocumentParsingError("PDF 页码必须从 1 开始")
        if block_index < 0:
            raise DocumentParsingError("PDF Block 索引不能为负数")

        try:
            with pymupdf.open(safe_path) as pdf:
                if pdf.needs_pass:
                    if password is None:
                        raise DocumentParsingError(
                            "PDF 受打开密码保护，历史记录未保存密码，无法提取图片"
                        )
                    if not pdf.authenticate(password):
                        raise DocumentParsingError("PDF 打开密码错误")
                if page > pdf.page_count:
                    raise DocumentParsingError(
                        f"PDF 页码 {page} 超出总页数 {pdf.page_count}"
                    )
                raw_blocks = pdf[page - 1].get_text("dict").get("blocks", [])
                if block_index >= len(raw_blocks):
                    raise DocumentParsingError(
                        f"PDF 图片 Block 不存在: 第 {page} 页索引 {block_index}"
                    )
                raw_block = raw_blocks[block_index]
                if raw_block.get("type") != 1:
                    raise DocumentParsingError(
                        f"指定区域不是图片 Block: 第 {page} 页索引 {block_index}"
                    )
                image_bytes = raw_block.get("image")
                if not isinstance(image_bytes, bytes) or not image_bytes:
                    raise DocumentParsingError("PDF 图片 Block 不包含可提取的图片数据")
                extension = str(raw_block.get("ext") or "").lower()
                media_types = {
                    "jpeg": "image/jpeg",
                    "jpg": "image/jpeg",
                    "png": "image/png",
                    "gif": "image/gif",
                    "webp": "image/webp",
                }
                if extension in media_types:
                    return image_bytes, media_types[extension]
                pixmap = pymupdf.Pixmap(image_bytes)
                return pixmap.tobytes("png"), "image/png"
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"PDF 图片提取失败: {exc}") from exc

    def _validate_path(self, path: Path) -> Path:
        """验证输入路径、扩展名和大小，不接受目录或非 PDF 文件。"""

        safe_path = path.expanduser().resolve()
        if not safe_path.is_file():
            raise DocumentParsingError(f"PDF 文件不存在: {safe_path}")
        if safe_path.suffix.lower() != ".pdf":
            raise DocumentParsingError("只支持 .pdf 文件")
        file_size = safe_path.stat().st_size
        if file_size > self.max_file_size:
            raise DocumentParsingError(
                f"PDF 大小 {file_size} 字节超过限制 {self.max_file_size}"
            )
        return safe_path

    @staticmethod
    def _hash_file(path: Path) -> str:
        """流式计算文件摘要，生成稳定且不暴露文件名的文档 ID。"""

        digest = sha256()
        with path.open("rb") as file_handle:
            while chunk := file_handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _parse_page(self, pdf_page: pymupdf.Page, document_id: str) -> Page:
        """把一页 PDF 的原始字典转换为 Block 列表。"""

        page_number = pdf_page.number + 1
        raw_page = pdf_page.get_text("dict")
        blocks: list[Block] = []

        for block_index, raw_block in enumerate(raw_page.get("blocks", [])):
            block_type = raw_block.get("type")
            if block_type == 0:
                blocks.extend(
                    self._parse_text_block(raw_block, page_number, block_index)
                )
            elif block_type == 1:
                image_block = self._parse_image_block(
                    raw_block, page_number, block_index
                )
                if image_block is not None:
                    blocks.append(image_block)

        # T39 阶段 1：矢量填充只枚举一次，背景统计与类型信号共用。
        vector_fills, drawing_errors = self._page_vector_fills(pdf_page)
        page_area = float(pdf_page.rect.width * pdf_page.rect.height)
        # 整页级填充（页面底色）不属于任何元素的形状特征，从类型
        # 信号中剔除，只保留在背景统计里——否则每个块都会被底色
        # 记一次"全覆盖"，信号失去区分度。
        shape_fills = [
            (rect, fill)
            for rect, fill in vector_fills
            if rect.width * rect.height < page_area * self.background.background_min_area_ratio
        ]
        background_color, dark_boxes, background_errors = self._page_background(
            pdf_page, vector_fills, drawing_errors
        )
        page_metadata = {
            "rotation": int(pdf_page.rotation),
            # 页面背景色（#RRGGBB 或 None）：供"隐形文字"检测判断
            # 文字颜色是否与页面整体背景同色。
            "background_color": background_color,
            # 深色填充块与图片的 bbox 列表：白字落在其上时是正常
            # 设计（黑底白字、图上白字），隐形检测需按区域排除。
            "dark_boxes": dark_boxes,
        }
        if background_errors:
            # 背景/深色块提取失败会让隐形文字检测对该页降级（漏报
            # 白字白底）；契约 §9 禁止静默跳过，失败类型必须随报告
            # 可见，供验收人判断该页检测能力的可信度。
            page_metadata["background_parse_errors"] = background_errors
        page_area = float(pdf_page.rect.width * pdf_page.rect.height)
        for block in blocks:
            self._attach_typing_signals(block, shape_fills, page_area)
        return Page(
            document_id=document_id,
            page=page_number,
            width=float(pdf_page.rect.width),
            height=float(pdf_page.rect.height),
            blocks=blocks,
            metadata=page_metadata,
        )

    def _page_vector_fills(
        self, pdf_page: pymupdf.Page
    ) -> tuple[list[tuple[Any, Any]], list[str]]:
        """枚举页面全部带填充的矢量绘图，返回 ((rect, fill), 失败记录)。

        供背景统计与 T39 类型信号共用；描边类绘图（无 fill）不进入
        清单。个别异常 PDF 的枚举可能抛错——返回空清单并记录失败
        类型，与背景统计的降级语义一致。
        """

        fills: list[tuple[Any, Any]] = []
        errors: list[str] = []
        try:
            for drawing in pdf_page.get_drawings():
                rect = drawing.get("rect")
                fill = drawing.get("fill")
                if rect is None or fill is None:
                    continue
                fills.append((rect, fill))
        except Exception as exc:
            errors.append(f"get_drawings:{type(exc).__name__}")
        return fills, errors

    def _attach_typing_signals(
        self,
        block: Block,
        vector_fills: list[tuple[Any, Any]],
        page_area: float,
    ) -> None:
        """把类型推断所需的解析信号写入 block.metadata（T39 阶段 1）。

        纯沉淀：当前无任何下游消费，报告也不含 Block——失败或缺失
        不影响任何检测行为。信号语义见 docs/region-typing-design.md。
        """

        signals: dict[str, Any] = {}
        bbox = block.bbox
        block_area = bbox.width * bbox.height
        if block.type == ElementType.TEXT:
            text = block.content.text if block.content else ""
            chars = len(text)
            signals["chars"] = chars
            if chars:
                signals["digit_density"] = round(
                    sum(1 for ch in text if ch.isdigit()) / chars, 4
                )
                # 坐标轴标签/图例的典型形态是短文本。
                signals["short_text"] = chars <= 8
            font = block.style.font_family if block.style else None
            if font:
                lowered = font.lower()
                signals["math_font"] = any(
                    marker in lowered for marker in ("math", "symbol", "stix")
                )
        # 与带填充矢量图形的重叠统计：图表/表格/形状分类的核心特征。
        if block_area > 0:
            intersect_total = 0.0
            fill_colors: set[str] = set()
            fill_count = 0
            for rect, fill in vector_fills:
                inter_x = min(bbox.right, rect.x1) - max(bbox.x, rect.x0)
                inter_y = min(bbox.bottom, rect.y1) - max(bbox.y, rect.y0)
                if inter_x <= 0 or inter_y <= 0:
                    continue
                fill_count += 1
                intersect_total += inter_x * inter_y
                if isinstance(fill, (tuple, list)) and len(fill) >= 3:
                    red, green, blue = (
                        max(0, min(255, int(round(float(channel) * 255))))
                        for channel in fill[:3]
                    )
                    fill_colors.add(f"#{red:02X}{green:02X}{blue:02X}")
            signals["vector_fill_count"] = fill_count
            signals["vector_fill_color_count"] = len(fill_colors)
            signals["vector_fill_area_ratio"] = round(
                min(1.0, intersect_total / block_area), 4
            )
        if block.type == ElementType.IMAGE and page_area > 0:
            signals["page_area_ratio"] = round(block_area / page_area, 4)
        block.metadata["typing_signals"] = signals

    def _page_background(
        self,
        pdf_page: pymupdf.Page,
        vector_fills: list[tuple[Any, Any]],
        drawing_errors: list[str],
    ) -> tuple[str | None, list[dict[str, float]], list[str]]:
        """提取页面背景色、深色背景块与提取失败记录。

        返回 (背景色, 深色块列表, 失败记录)。背景色取覆盖面积最大的
        整页填充矩形颜色；找不到大面积填充时为 None。深色块包括非
        浅色填充矩形与全部图片。矢量清单由 _page_vector_fills 预先
        枚举（与类型信号共用一次 get_drawings）；图片枚举仍可能抛错
        ——按无背景降级处理，但失败类型写入报告而不是静默吞掉。
        """

        settings = self.background
        page_area = pdf_page.rect.width * pdf_page.rect.height
        dark_boxes: list[dict[str, float]] = []
        errors: list[str] = list(drawing_errors)
        largest: tuple[float, tuple[float, float, float] | None] | None = None
        for rect, fill in vector_fills:
            area = rect.width * rect.height
            if area < page_area * settings.dark_box_min_area_ratio:
                # 过小的装饰块不影响文字可见性判断。
                continue
            is_dark = min(fill) < settings.dark_fill_max_channel
            if is_dark:
                dark_boxes.append(
                    {
                        "x": rect.x0,
                        "y": rect.y0,
                        "width": rect.width,
                        "height": rect.height,
                    }
                )
            if area >= page_area * settings.background_min_area_ratio and not is_dark:
                # 浅色整页填充才是页面背景色；深色整页填充进 dark_boxes。
                if largest is None or area > largest[0]:
                    largest = (area, fill)
        # 图片视为非浅色背景块：白字在图片上正常可见（图片可能是
        # 深色照片，也可能是浅色插画——统一跳过避免误判）。
        try:
            for info in pdf_page.get_image_info():
                bbox = info.get("bbox")
                if bbox is None:
                    continue
                dark_boxes.append(
                    {
                        "x": bbox[0],
                        "y": bbox[1],
                        "width": bbox[2] - bbox[0],
                        "height": bbox[3] - bbox[1],
                    }
                )
        except Exception as exc:
            errors.append(f"get_image_info:{type(exc).__name__}")
        if largest is None:
            return None, dark_boxes, errors
        red, green, blue = (max(0.0, min(1.0, channel)) for channel in largest[1])
        color = f"#{int(round(red * 255)):02X}{int(round(green * 255)):02X}{int(round(blue * 255)):02X}"
        return color, dark_boxes, errors

    def _parse_text_block(
        self,
        raw_block: dict[str, Any],
        page_number: int,
        block_index: int,
    ) -> list[Block]:
        """按 Span 建立文本 Block，以保留字体和局部边界框变化。"""

        blocks: list[Block] = []
        for line_index, line in enumerate(raw_block.get("lines", [])):
            for span_index, span in enumerate(line.get("spans", [])):
                bbox = self._build_bbox(span.get("bbox"))
                if bbox is None:
                    continue
                flags = int(span.get("flags", 0))
                block_id = (
                    f"p{page_number}-b{block_index}-l{line_index}-s{span_index}"
                )
                blocks.append(
                    Block(
                        id=block_id,
                        page=page_number,
                        type=ElementType.TEXT,
                        bbox=bbox,
                        style=TextStyle(
                            font_family=span.get("font"),
                            font_size=self._positive_float(span.get("size")),
                            # PyMuPDF 的字体 flags 中第 5 位表示粗体，第 2 位表示斜体。
                            font_weight=700 if flags & 16 else 400,
                            italic=bool(flags & 2),
                            color=self._format_color(span.get("color")),
                        ),
                        content=Content(text=span.get("text", "")),
                        metadata={
                            "source_block_index": block_index,
                            "source_line_index": line_index,
                            "source_span_index": span_index,
                            # PyMuPDF alpha 为 0～255；统一保存为 0～1，
                            # 供检测器区分可见正文与透明检索文本层。
                            "opacity": self._opacity(span.get("alpha")),
                        },
                    )
                )
        return blocks

    @staticmethod
    def _opacity(value: Any) -> float | None:
        """把 PDF 文本 alpha 归一化为 0～1；旧引擎缺字段时保持未知。"""

        if not isinstance(value, (int, float)):
            return None
        return max(0.0, min(1.0, float(value) / 255.0))

    def _parse_image_block(
        self,
        raw_block: dict[str, Any],
        page_number: int,
        block_index: int,
    ) -> Block | None:
        """记录图片位置和可序列化属性，不把图片二进制写入模型。"""

        bbox = self._build_bbox(raw_block.get("bbox"))
        if bbox is None:
            return None
        extension = raw_block.get("ext")
        image_digest = self._image_content_digest(raw_block.get("image"))
        return Block(
            id=f"p{page_number}-b{block_index}-image",
            page=page_number,
            type=ElementType.IMAGE,
            bbox=bbox,
            content=Content(asset_ref=f"block-{block_index}.{extension or 'bin'}"),
            metadata={
                "source_block_index": block_index,
                "width": raw_block.get("width"),
                "height": raw_block.get("height"),
                "extension": extension,
                # 对解码后的像素采样计算摘要，忽略 PNG/JPEG 重新编码差异；
                # Detector 只消费摘要，不把图片二进制泄漏到 Schema。
                "content_sha256": image_digest,
            },
        )

    @staticmethod
    def _image_content_digest(value: Any) -> str | None:
        """计算内嵌图片的稳定像素摘要，异常编码退回原始字节摘要。"""

        if not isinstance(value, bytes) or not value:
            return None
        try:
            pixmap = pymupdf.Pixmap(value)
            digest = sha256()
            digest.update(
                f"{pixmap.width}:{pixmap.height}:{pixmap.n}:{int(pixmap.alpha)}".encode()
            )
            digest.update(pixmap.samples)
            return digest.hexdigest()
        except Exception:
            return sha256(value).hexdigest()

    @staticmethod
    def _build_bbox(raw_bbox: Any) -> BoundingBox | None:
        """把 PyMuPDF 的 x0/y0/x1/y1 转换为项目的 x/y/width/height。"""

        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
            return None
        x0, y0, x1, y1 = (float(value) for value in raw_bbox)
        width = x1 - x0
        height = y1 - y0
        # 空 Span 可能产生零面积框；它们不具备布局比较价值，因此直接忽略。
        if width <= 0 or height <= 0:
            return None
        return BoundingBox(x=x0, y=y0, width=width, height=height)

    @staticmethod
    def _positive_float(value: Any) -> float | None:
        """只返回可用于样式比较的正数。"""

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @staticmethod
    def _format_color(value: Any) -> str | None:
        """把 PyMuPDF 的整数 RGB 颜色转换为稳定的十六进制字符串。"""

        if not isinstance(value, int):
            return None
        return f"#{value & 0xFFFFFF:06X}"
