"""区域匹配使用的几何相似度函数。"""

from math import hypot

from document_qa.schemas import BoundingBox


def position_similarity(
    source: BoundingBox,
    target: BoundingBox,
    page_width: float,
    page_height: float,
) -> float:
    """按页面对角线归一化区域中心距离。"""

    source_center = (source.x + source.width / 2, source.y + source.height / 2)
    target_center = (target.x + target.width / 2, target.y + target.height / 2)
    distance = hypot(
        target_center[0] - source_center[0], target_center[1] - source_center[1]
    )
    diagonal = hypot(page_width, page_height)
    return max(0.0, 1.0 - distance / diagonal) if diagonal else 0.0


def size_similarity(source: BoundingBox, target: BoundingBox) -> float:
    """分别比较宽高比例，避免面积相同但形状完全不同的误匹配。"""

    # Schema 校验已保证宽高为正，这里仍做防御，兼容绕过校验的调用方。
    max_width = max(source.width, target.width)
    max_height = max(source.height, target.height)
    if max_width <= 0 or max_height <= 0:
        return 0.0
    width_score = min(source.width, target.width) / max_width
    height_score = min(source.height, target.height) / max_height
    return (width_score + height_score) / 2


def intersection_ratio(first: BoundingBox, second: BoundingBox) -> float:
    """返回交集面积占较小区域面积的比例。"""

    overlap_width = max(0.0, min(first.right, second.right) - max(first.x, second.x))
    overlap_height = max(
        0.0, min(first.bottom, second.bottom) - max(first.y, second.y)
    )
    intersection = overlap_width * overlap_height
    return intersection / min(first.area, second.area) if intersection else 0.0

