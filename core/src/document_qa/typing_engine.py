"""区域类型推断器（T39 阶段 2，shadow）。

消费解析器沉淀的 `typing_signals`，把区域语义类型写入
`region.metadata["semantic_type"]`（type + confidence + evidence）。
阶段 2 为纯 shadow：类型标签不被任何检测/匹配逻辑消费，报告不含
Region，Golden 逐位不变。

设计原则（docs/region-typing-design.md §2）：保守分类——置信度不足
一律不打标签（下游按现状处理）；分类依据写入 evidence 可审计。
配置为引擎级常量：消费端（阶段 3）落地时随 Golden 更新迁入
RuleProfile.typing，理由与 T38 相同（Profile 全量快照进报告）。
"""

from dataclasses import dataclass, field

from document_qa.schemas import Document, Page, Region

# 置信度档位：达到 high 才算"可依赖"的标签；medium 标签供阶段 3
# 消费端按需取用（低风险豁免），low 一律不打标签。
_HIGH = "high"
_MEDIUM = "medium"

# 页眉/页脚判定：顶部/底部带高度占页比与重复出现页占比下限。
_BAND_RATIO = 0.12
_HEADER_FOOTER_MIN_PAGE_RATIO = 0.6
_HEADER_FOOTER_MIN_PAGES = 3

# 位图图表：图片区域面积占页比下限与周边短标签数下限。
_CHART_BITMAP_MIN_AREA = 0.08
_CHART_BITMAP_MIN_LABELS = 2
# 环绕标签搜索的外扩比例（相对区域最大边）。
_LABEL_SEARCH_RATIO = 0.18

# 矢量图表标签：区域被填充覆盖的比例下限（实心色块特征）。
_CHART_VECTOR_MIN_FILL_RATIO = 0.5
_CHART_VECTOR_MIN_FILLS = 3

# 表格：细网格线特征——填充次数多而覆盖率低，且子块存在共线左边缘。
_TABLE_MIN_FILLS = 6
_TABLE_MAX_FILL_RATIO = 0.25

# 公式：数学字体命中的子块 + 区域文本长度上限。
_FORMULA_MAX_CHARS = 60


@dataclass
class _RegionSignal:
    """把区域子块的 typing_signals 聚合后的视图。"""

    max_fill_count: int = 0
    max_fill_ratio: float = 0.0
    max_page_area_ratio: float = 0.0
    digit_density: float = 0.0
    chars: int = 0
    short_text: bool = False
    math_font: bool = False
    child_left_edges: list[float] = field(default_factory=list)


def _region_signal(page: Page, region: Region) -> _RegionSignal:
    """聚合区域全部子块的信号；无子块时返回空视图。"""

    blocks_by_id = {block.id: block for block in page.blocks}
    signal = _RegionSignal()
    digit_chars = 0.0
    left_edge_counts: dict[float, int] = {}
    for block_id in region.children:
        block = blocks_by_id.get(block_id)
        if block is None:
            continue
        signals = block.metadata.get("typing_signals") or {}
        signal.max_fill_count = max(
            signal.max_fill_count, int(signals.get("vector_fill_count", 0) or 0)
        )
        signal.max_fill_ratio = max(
            signal.max_fill_ratio, float(signals.get("vector_fill_area_ratio", 0.0) or 0.0)
        )
        signal.max_page_area_ratio = max(
            signal.max_page_area_ratio,
            float(signals.get("page_area_ratio", 0.0) or 0.0),
        )
        if signals.get("math_font"):
            signal.math_font = True
        if signals.get("short_text"):
            signal.short_text = True
        chars = int(signals.get("chars", 0) or 0)
        signal.chars += chars
        if signals.get("digit_density") is not None and chars:
            digit_chars += chars * float(signals["digit_density"])
        left = round(block.bbox.x, 1)
        left_edge_counts[left] = left_edge_counts.get(left, 0) + 1
    if signal.chars:
        signal.digit_density = digit_chars / signal.chars
    # 左边缘共线：同一边缘出现 ≥2 个子块视为一列（表格列特征）。
    signal.child_left_edges = [
        x for x, count in left_edge_counts.items() if count >= 2
    ]
    return signal


def _normalize_header_text(text: str) -> str:
    """页眉页脚文本归一化：数字打码（页码逐页变化但属同一元素）。"""

    return "".join("#" if ch.isdigit() else ch for ch in text.strip())


class RegionTyping:
    """区域语义类型推断器（shadow：只写 region.metadata）。"""

    def __init__(self, *, enabled: bool = True) -> None:
        """enabled=False 时完全跳过（行为与无 Typing 版本一致）。"""

        self.enabled = enabled

    def annotate_document(self, document: Document) -> None:
        """为文档全部区域打语义类型标签（页级规则 + 跨页规则）。"""

        if not self.enabled:
            return
        header_footer = self._header_footer_labels(document)
        for page in document.pages:
            for region in page.regions:
                label = header_footer.get((page.page, region.id))
                if label is not None:
                    self._set(region, label)
                    continue
                label = self._page_level_label(page, region)
                if label is not None:
                    self._set(region, label)

    # ---- 页级规则 -----------------------------------------------------------

    def _page_level_label(self, page: Page, region: Region) -> dict | None:
        """页级类型规则：位图图表 > 公式 > 矢量图表标签 > 表格。"""

        signal = _region_signal(page, region)
        page_area = page.width * page.height

        if region.type.value == "image":
            if (
                page_area > 0
                and signal.max_page_area_ratio >= _CHART_BITMAP_MIN_AREA
            ):
                labels = self._surrounding_short_labels(page, region)
                confidence = _HIGH if labels >= _CHART_BITMAP_MIN_LABELS else _MEDIUM
                return {
                    "type": "chart",
                    "confidence": confidence,
                    "evidence": ["bitmap_area", f"surround_labels={labels}"],
                }
            return None

        if region.type.value not in ("text", "paragraph", "heading", "list"):
            return None

        if signal.math_font and signal.chars <= _FORMULA_MAX_CHARS:
            return {
                "type": "formula",
                "confidence": _HIGH,
                "evidence": ["math_font", f"chars={signal.chars}"],
            }

        if signal.max_fill_ratio >= _CHART_VECTOR_MIN_FILL_RATIO and (
            signal.short_text or signal.digit_density >= 0.3
        ):
            return {
                "type": "chart",
                "confidence": _MEDIUM,
                "evidence": [
                    f"fill_ratio={signal.max_fill_ratio}",
                    f"digit_density={round(signal.digit_density, 3)}",
                ],
            }

        if signal.max_fill_count >= _TABLE_MIN_FILLS and (
            signal.max_fill_ratio <= _TABLE_MAX_FILL_RATIO
        ) and signal.child_left_edges:
            return {
                "type": "table",
                "confidence": _MEDIUM,
                "evidence": [
                    f"fills={signal.max_fill_count}",
                    f"columns={len(signal.child_left_edges)}",
                ],
            }
        return None

    @staticmethod
    def _surrounding_short_labels(page: Page, region: Region) -> int:
        """统计位图区域外扩范围内紧邻的短文本标签数（图例/轴标签）。"""

        margin = max(region.bbox.width, region.bbox.height) * _LABEL_SEARCH_RATIO
        count = 0
        for other in page.regions:
            if other.id == region.id or other.type.value != "text":
                continue
            if not (other.content and other.content.text):
                continue
            if len(other.content.text.strip()) > 8:
                continue
            expanded_x0 = region.bbox.x - margin
            expanded_y0 = region.bbox.y - margin
            expanded_x1 = region.bbox.right + margin
            expanded_y1 = region.bbox.bottom + margin
            if (
                expanded_x0 <= other.bbox.x
                and other.bbox.right <= expanded_x1
                and expanded_y0 <= other.bbox.y
                and other.bbox.bottom <= expanded_y1
            ):
                count += 1
        return count

    # ---- 跨页规则 -----------------------------------------------------------

    def _header_footer_labels(
        self, document: Document
    ) -> dict[tuple[int, str], dict]:
        """跨页重复聚类：归一化文本在顶部/底部带重复出现的区域。"""

        if len(document.pages) < _HEADER_FOOTER_MIN_PAGES:
            return {}
        occurrences: dict[tuple[str, str], list[tuple[int, str]]] = {}
        for page in document.pages:
            band_height = page.height * _BAND_RATIO
            for region in page.regions:
                if region.type.value not in ("text", "paragraph"):
                    continue
                text = region.content.text if region.content else None
                if not text or not text.strip():
                    continue
                band = ""
                if region.bbox.bottom <= band_height:
                    band = "header"
                elif region.bbox.y >= page.height - band_height:
                    band = "footer"
                if not band:
                    continue
                key = (band, _normalize_header_text(text))
                occurrences.setdefault(key, []).append((page.page, region.id))
        labels: dict[tuple[int, str], dict] = {}
        total_pages = len(document.pages)
        for (band, _normalized), hits in occurrences.items():
            distinct_pages = {page_no for page_no, _ in hits}
            ratio = len(distinct_pages) / total_pages
            if (
                len(distinct_pages) >= _HEADER_FOOTER_MIN_PAGES
                and ratio >= _HEADER_FOOTER_MIN_PAGE_RATIO
            ):
                label = {
                    "type": "header" if band == "header" else "footer",
                    "confidence": _HIGH if ratio >= 0.9 else _MEDIUM,
                    "evidence": [
                        f"pages={len(distinct_pages)}/{total_pages}",
                        f"ratio={round(ratio, 2)}",
                    ],
                }
                for page_no, region_id in hits:
                    labels[(page_no, region_id)] = label
        return labels

    @staticmethod
    def _set(region: Region, label: dict) -> None:
        """把标签写入 region.metadata（不改动公开 type 字段）。"""

        region.metadata["semantic_type"] = label
