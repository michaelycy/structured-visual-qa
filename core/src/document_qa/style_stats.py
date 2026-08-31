"""分组与匹配共用的代表样式统计工具。"""

from __future__ import annotations


def weighted_median_font_size(entries: list[tuple[float, int]]) -> float | None:
    """按字符数加权的字号中位数，代表 Region 的主体文字字号。

    以最大字号块作代表会把「大标题 + 多行小字号正文」的合并 Region
    错标为标题字号；翻译导致的换行/合并使两侧取到不同子块时，字号
    变化检测既会假阳性也会漏报。按字符数加权的中位数反映读者实际
    看到的主体字号，对行数变化不敏感。
    """

    samples = [
        (size, max(1, weight)) for size, weight in entries if size and size > 0
    ]
    if not samples:
        return None
    samples.sort(key=lambda item: item[0])
    total = sum(weight for _size, weight in samples)
    cumulative = 0
    for size, weight in samples:
        cumulative += weight
        if cumulative * 2 >= total:
            return size
    return samples[-1][0]
