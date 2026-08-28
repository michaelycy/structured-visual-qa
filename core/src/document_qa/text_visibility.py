"""PDF 提取文本的 Unicode 可见性与控制字符归一化。"""

from __future__ import annotations

import unicodedata


_NON_VISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Mn", "Me", "Zl", "Zp", "Zs"})


def has_visible_text(value: str | None) -> bool:
    """判断文本是否至少包含一个可见字符。

    PDF 导出器可能留下零宽空格、BOM、软连字符、双向排版控制符或
    单独的组合附加符。这些字符单独存在时不形成可见内容，不应进入
    缺失、新增、重叠或不可见文字规则。
    """

    return any(
        not char.isspace()
        and unicodedata.category(char) not in _NON_VISIBLE_CATEGORIES
        for char in value or ""
    )


def normalize_extracted_text(value: str | None) -> str:
    """移除格式控制符并把不可见分隔符统一为空格。

    零宽格式符可能被插入数字或单词内部，直接删除可恢复原始 token；
    普通空白及换行分隔符保留为空格，避免把两个独立 token 意外拼接。
    """

    normalized: list[str] = []
    for char in value or "":
        category = unicodedata.category(char)
        if category == "Cf" or (category == "Cc" and not char.isspace()):
            continue
        if char.isspace() or category in {"Zl", "Zp", "Zs"}:
            normalized.append(" ")
            continue
        normalized.append(char)
    return "".join(normalized)
