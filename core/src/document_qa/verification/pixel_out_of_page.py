"""content_out_of_page 的渲染实证（T38 P1 验证器）。

主张："内容越出页面边界"。渲染只能呈现页面内的部分，因此实证
策略：bbox 与页面的交集为空（完全页外）→ 主张成立 confirmed；
交集区渲染后内容像素占比低于阈值（页内根本没有可见内容，越界
只是解析测量噪声）→ rejected；页内确有可见内容 → confirmed。
"""

from typing import Any

import numpy as np

from document_qa.schemas import Issue
from document_qa.verification.settings import VerificationSettings

_MAX_RGB_DISTANCE = 441.67


def verify_content_out_of_page(
    issue: Issue,
    *,
    page_width: float,
    page_height: float,
    page_pixels: tuple[int, int, bytes],
    settings: VerificationSettings,
) -> dict[str, Any]:
    """对一条 content_out_of_page 做渲染实证，返回裁决与证据数值。"""

    import time

    started = time.perf_counter()
    evidence: dict[str, Any] = {
        "method": "in_page_content_ratio",
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
    scale = settings.dpi / 72.0
    width, height, samples = page_pixels
    # bbox 与页面的像素交集；为空即完全页外，主张成立。
    x0 = max(0, int(issue.bbox.x * scale))
    y0 = max(0, int(issue.bbox.y * scale))
    x1 = min(width, int(np.ceil(issue.bbox.right * scale)))
    y1 = min(height, int(np.ceil(issue.bbox.bottom * scale)))
    if x1 <= x0 or y1 <= y0:
        return finish("confirmed", "fully_outside_page")

    image = np.frombuffer(samples, dtype=np.uint8).reshape(height, width, 3)
    crop = image[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    evidence["sample_count"] = int(crop.shape[0])
    # 页内可见内容占比：与裁切区中位色（背景）色距超容差的像素比例。
    background = np.median(crop, axis=0)
    distances = np.linalg.norm(crop - background, axis=1) / _MAX_RGB_DISTANCE
    content_ratio = float((distances > settings.glyph_color_tolerance).mean())
    evidence["in_page_content_ratio"] = round(content_ratio, 5)
    evidence["threshold_used"] = settings.min_visible_content_ratio
    if content_ratio < settings.min_visible_content_ratio:
        return finish("rejected", "no_visible_in_page_content")
    return finish("confirmed", "visible_content_crosses_page_edge")
