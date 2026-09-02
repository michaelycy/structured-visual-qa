"""invisible_text 的像素对比度实证（T38 P0 验证器）。

主张："目标文字在页面上不可见"。实证方法：按验证 dpi 渲染目标页，
在 Issue bbox 内做像素采样——按文字色把像素分为"字形候选"与"背景
参照"两群，字形候选与背景中位色的归一化色距即为可见性对比度。

裁决原则是 fail-open：找不到字形像素、无法建立背景基准、渲染失败
等一切不确定情形都维持检测器原判（confirmed），只有拿到"文字与
背景对比度 ≥ 阈值"的正向证据才 rejected。T29 的手工闭环（白字落在
彩色饼图扇区上，渲染对比度极高 → 38 条误报）是本验证器的标定用例。
"""

import time
from typing import Any

import numpy as np

from document_qa.schemas import Issue, Page
from document_qa.verification.settings import VerificationSettings

# 归一化色距的分母：RGB 空间最大欧氏距离 sqrt(3 * 255^2)。
_MAX_RGB_DISTANCE = 441.67


def hex_to_rgb(color: str | None) -> tuple[int, int, int] | None:
    """把 #RRGGBB 颜色串转为 RGB 三元组；格式非法返回 None。"""

    if not color or not color.startswith("#") or len(color) != 7:
        return None
    try:
        return (
            int(color[1:3], 16),
            int(color[3:5], 16),
            int(color[5:7], 16),
        )
    except ValueError:
        return None


def verify_invisible_text(
    issue: Issue,
    *,
    target_page: Page,
    page_pixels: tuple[int, int, bytes],
    settings: VerificationSettings,
) -> dict[str, Any]:
    """对一条 invisible_text 做渲染实证，返回裁决与证据数值。"""

    started = time.perf_counter()
    evidence: dict[str, Any] = {
        "method": "pixel_contrast",
        "dpi": settings.dpi,
        "verdict": "confirmed",
    }

    def finish(verdict: str, reason: str, **values: Any) -> dict[str, Any]:
        evidence["verdict"] = verdict
        evidence["reason"] = reason
        evidence.update(values)
        evidence["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return evidence

    if issue.bbox is None:
        return finish("unverified", "missing_bbox")
    text_rgb = hex_to_rgb(issue.metrics.get("text_color") if issue.metrics else None)
    if text_rgb is None:
        return finish("unverified", "no_text_color")

    width, height, samples = page_pixels
    scale = settings.dpi / 72.0
    # bbox → 像素矩形，裁剪到页面范围内。
    x0 = max(0, int(issue.bbox.x * scale))
    y0 = max(0, int(issue.bbox.y * scale))
    x1 = min(width, int(np.ceil(issue.bbox.right * scale)))
    y1 = min(height, int(np.ceil(issue.bbox.bottom * scale)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return finish("unverified", "bbox_too_small")

    image = np.frombuffer(samples, dtype=np.uint8).reshape(height, width, 3)
    crop = image[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    evidence["sample_count"] = int(crop.shape[0])

    distances = np.linalg.norm(crop - np.asarray(text_rgb, dtype=np.float32), axis=1) / _MAX_RGB_DISTANCE
    glyph_mask = distances <= settings.glyph_color_tolerance
    glyph_fraction = float(glyph_mask.mean())
    evidence["glyph_fraction"] = round(glyph_fraction, 5)
    if glyph_fraction < settings.min_glyph_fraction:
        # 渲染结果里几乎没有文字色像素：真透明（alpha≈0）或字形过细，
        # 无法建立"可见"的正向证据，维持原判。
        return finish("confirmed", "glyph_pixels_not_found")

    background_pixels = crop[~glyph_mask]
    background_fraction = float(background_pixels.shape[0] / crop.shape[0])
    evidence["background_fraction"] = round(background_fraction, 5)
    if background_fraction < settings.min_background_fraction:
        return finish("confirmed", "no_background_reference")

    background_color = np.median(background_pixels, axis=0)
    contrast = float(
        np.linalg.norm(background_color - np.asarray(text_rgb, dtype=np.float32))
        / _MAX_RGB_DISTANCE
    )
    evidence["text_pixel_contrast"] = round(contrast, 4)
    evidence["threshold_used"] = settings.min_visible_contrast
    if contrast >= settings.min_visible_contrast:
        return finish("rejected", "text_visible_on_background")
    return finish("confirmed", "text_blends_into_background")
