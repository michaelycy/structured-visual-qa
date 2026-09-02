"""跨检测器共享的脚本识别与语言场景解析。

ContentDetector（漏译/数字一致性）、RasterOCRDetector（图像化漏译）
与 RuleDetector（language_overrides 解析）必须对同一页面得出一致的
主导脚本结论；判定表此前在多个模块各自维护并已发生漂移（如假名
归属、阿语数字区间），这里收敛为单一事实来源。
"""

from __future__ import annotations

import re
from collections import Counter

from document_qa.profiles import RuleProfile
from document_qa.schemas import Region
from document_qa.text_visibility import has_visible_text

# 参与脚本投票与漏译判定的文字区块：名称即语言场景标识（language 维度）
# 中的脚本名。中英互译沿用 "cjk"/"latin"，新增语言按 Unicode 区块补充。
SCRIPT_PATTERNS: dict[str, re.Pattern[str]] = {
    "latin": re.compile(r"[A-Za-z]"),
    "cjk": re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]"),
    # 阿拉伯字母区间排除了阿拉伯-印度数字（U+0660-0669）与标点，
    # 否则数字串会参与"文字占比"统计。
    "arabic": re.compile(r"[\u0620-\u064a\u066e-\u06d3]"),
    "hebrew": re.compile(r"[\u05b0-\u05ea]"),
    "cyrillic": re.compile(r"[\u0400-\u04ff]"),
    "greek": re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]"),
    "devanagari": re.compile(r"[\u0900-\u097f]"),
    "bengali": re.compile(r"[\u0980-\u09ff]"),
    "thai": re.compile(r"[\u0e00-\u0e7f]"),
    "hangul": re.compile(r"[\uac00-\ud7af\u1100-\u11ff]"),
    "kana": re.compile(r"[\u3040-\u30ff]"),
}


# 全部脚本字母的并集匹配：漏译判定中"字母总数"的分母。
ANY_SCRIPT_PATTERN = re.compile(
    "|".join(f"(?:{pattern.pattern})" for pattern in SCRIPT_PATTERNS.values())
)

# 全角（等宽 1em）字符区间：用于字符 advance 估算，服务尺寸类检测的
# 跨语言密度归一。刻意比 SCRIPT_PATTERNS 更宽——这里关心的是"占多宽"
# 而非"属于哪种文字"，因此纳入兼容表意文字（U+F900 起，翻译 PDF 常
# 见）、CJK 标点与全角形式；SCRIPT_PATTERNS 服务脚本投票，两表语义
# 不同，不得互相替代。
FULLWIDTH_PATTERN = re.compile(
    r"[\u2e80-\u9fff\uf900-\ufaff\u3000-\u303f\u3040-\u30ff"
    r"\uac00-\ud7af\uff00-\uffef]"
)


def text_advance_units(text: str) -> float:
    """按全角 1.0em、半角 0.5em 估算文本的排版长度（em 单位）。

    竖排/旋转文本沿书写轴的 BBox 长度近似等于"字符数 × 单字 advance"，
    而 CJK 字符（约 1em）与拉丁字符（约 0.5em）密度相差一倍，直接比较
    字符数或 BBox 尺寸都会把正常翻译适配误判为剧变。空格与标点按半角
    计（略高估拉丁串长度，使豁免更保守）；不可见字符不计。
    """

    units = 0.0
    for char in text:
        if char == " ":
            # 空格占半角 advance，计入墨迹长度。
            units += 0.5
        elif char.isprintable() and not char.isspace():
            # 换行、制表等控制字符不占墨迹，跳过。
            units += 1.0 if FULLWIDTH_PATTERN.match(char) else 0.5
    return units


def dominant_script(regions: list[Region]) -> str | None:
    """按各 Region 主脚本的数量投票判断页面主导脚本。

    用区域数而非字符数投票：英文单词字母多、中文汉字信息密度高，
    按字符数统计会把"中文为主夹一段英文"的页面误判为英文。
    """

    votes: Counter = Counter()
    for region in regions:
        # 图片等 Region 的 content.text 可能为 None，需先判空。
        text = region.content.text if region.content else ""
        if not has_visible_text(text):
            continue
        counts = {
            name: len(pattern.findall(text))
            for name, pattern in SCRIPT_PATTERNS.items()
        }
        top_two = sorted(counts.items(), key=lambda kv: -kv[1])[:2]
        if top_two[0][1] == 0:
            continue
        # 平票的 Region 不投票：中英对照的 Region 没有明确主脚本。
        if len(top_two) > 1 and top_two[0][1] == top_two[1][1]:
            continue
        votes[top_two[0][0]] += 1
    if not votes:
        return None
    top = votes.most_common(2)
    # 平票视为混排，无法定义"源语言"，漏译判定跳过。
    if len(top) == 2 and top[0][1] == top[1][1]:
        return "mixed"
    return top[0][0]


def dominant_script_by_characters(regions: list[Region]) -> str | None:
    """按全页字符总量判断主脚本，供图像化区域翻译方向识别。"""

    counts: Counter = Counter()
    for region in regions:
        text = region.content.text if region.content else None
        if not has_visible_text(text):
            continue
        for name, pattern in SCRIPT_PATTERNS.items():
            counts[name] += len(pattern.findall(text or ""))
    positive = [(name, count) for name, count in counts.items() if count > 0]
    if not positive:
        return None
    top = sorted(positive, key=lambda item: (-item[1], item[0]))
    if len(top) > 1 and top[0][1] == top[1][1]:
        return "mixed"
    return top[0][0]


def dominant_script_of_text(text: str) -> str | None:
    """按字符计数判断单段文本的主导脚本；无法判定或平票返回 None。

    与 Region 级函数共用同一张 SCRIPT_PATTERNS 判定表，保证碎片、
    漏译等检测器对同一段文本得出一致的脚本结论。
    """

    counts = {
        name: len(pattern.findall(text))
        for name, pattern in SCRIPT_PATTERNS.items()
    }
    top_two = sorted(counts.items(), key=lambda kv: -kv[1])[:2]
    if top_two[0][1] == 0:
        return None
    if len(top_two) > 1 and top_two[0][1] == top_two[1][1]:
        return None
    return top_two[0][0]


def resolve_language(
    profile: RuleProfile, source_regions: list[Region], target_regions: list[Region]
) -> str:
    """解析当前比较的语言场景标识（源脚本-目标脚本）。

    显式声明的 language 优先（用户比自动推断更清楚翻译方向）；
    auto 模式按双方主导脚本拼接，任一侧无法判定或同脚本时回退
    全局默认配置（场景键不会命中任何覆盖）。
    """

    if profile.language != "auto":
        return profile.language
    source_script = dominant_script(source_regions)
    target_script = dominant_script(target_regions)
    if not source_script or not target_script or source_script == target_script:
        return "default"
    return f"{source_script}-{target_script}"
