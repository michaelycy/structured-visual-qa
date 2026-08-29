"""跨语言数量语义归一：日期、金额、比例与带倍率数量。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


@dataclass(frozen=True)
class QuantityMention:
    """一处可比较的数量表达，key 用于守恒比较，display 用于报告证据。"""

    key: str
    display: str
    span: tuple[int, int]


_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_SMALL_UNITS = {"十": 10, "百": 100, "千": 1000}
_CHINESE_NUMBER = r"[零〇一二两三四五六七八九十百千]+"
_DECIMAL_OR_CHINESE = rf"(?:\d+(?:\.\d+)?|{_CHINESE_NUMBER})"

_ENGLISH_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_NAMES = "|".join(_ENGLISH_MONTHS)
_ENGLISH_MONTH_RANGE = re.compile(
    rf"\b(?P<start>{_MONTH_NAMES})\s+(?:to|through|-)\s+"
    rf"(?P<end>{_MONTH_NAMES})(?=\s+\d{{4}}\b)",
    re.IGNORECASE,
)
_ENGLISH_MONTH_DATE = re.compile(
    rf"\b(?P<leading>{_MONTH_NAMES})\b(?=\s+\d{{1,4}}\b)|"
    rf"\b\d{{1,2}}\s+(?P<trailing>{_MONTH_NAMES})\b",
    re.IGNORECASE,
)
_CHINESE_MONTH_RANGE = re.compile(
    rf"(?P<start>{_DECIMAL_OR_CHINESE})\s*(?:-|—|–|至|到)\s*"
    rf"(?P<end>{_DECIMAL_OR_CHINESE})\s*月"
)
_CHINESE_MONTH = re.compile(rf"(?P<month>{_DECIMAL_OR_CHINESE})\s*月")

_CHINESE_SCALED = re.compile(
    rf"(?P<number>{_DECIMAL_OR_CHINESE})\s*(?P<scale>万|亿)\s*"
    r"(?P<currency>人民币|元|美元|美金|欧元)?"
)
_CHINESE_SCALED_RANGE = re.compile(
    rf"(?P<start>{_DECIMAL_OR_CHINESE})\s*(?:-|—|–|至|到)\s*"
    rf"(?P<end>{_DECIMAL_OR_CHINESE})\s*(?P<scale>万|亿)\s*"
    r"(?P<currency>人民币|元|美元|美金|欧元)?"
)
_ENGLISH_SCALED = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*"
    r"(?P<scale>thousand|million|billion)\s*"
    r"(?P<currency>rmb|yuan|cny|usd|us dollars?|dollars?|euros?|eur)?\b",
    re.IGNORECASE,
)
_ENGLISH_SCALED_RANGE = re.compile(
    r"(?P<start>\d+(?:\.\d+)?)\s*(?:-|—|–|to|through)\s*"
    r"(?P<end>\d+(?:\.\d+)?)\s*"
    r"(?P<scale>thousand|million|billion)\s*"
    r"(?P<currency>rmb|yuan|cny|usd|us dollars?|dollars?|euros?|eur)?\b",
    re.IGNORECASE,
)

_CHINESE_PERCENT = re.compile(
    rf"(?P<modifier>超过|高于|低于|少于|不到|约|大约|近)?"
    rf"百分之(?P<number>{_DECIMAL_OR_CHINESE})"
)
_CHINESE_RATIO = re.compile(
    rf"(?P<modifier>超过|高于|低于|少于|不到|约|大约|近)?"
    rf"(?P<number>{_DECIMAL_OR_CHINESE})成"
)
_CHINESE_HALF = re.compile(
    r"(?P<modifier>超过|高于|低于|少于|不到|约|大约|近)?一半"
)
_NUMERIC_PERCENT = re.compile(
    r"(?P<modifier>超过|高于|低于|少于|不到|约|大约|近|"
    r"more\s+than|over|above|less\s+than|under|below|"
    r"about|approximately|around)?\s*"
    r"(?P<number>\d+(?:\.\d+)?)\s*(?:%|percent\b)",
    re.IGNORECASE,
)
_ENGLISH_HALF = re.compile(
    r"\b(?P<modifier>more\s+than|over|above|less\s+than|under|below|"
    r"about|approximately|around)?\s*half\b",
    re.IGNORECASE,
)

_SCALE_FACTORS = {
    "万": Decimal("10000"),
    "亿": Decimal("100000000"),
    "thousand": Decimal("1000"),
    "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
}
def _chinese_integer(text: str) -> int | None:
    """解析上下文明确的中文整数；不在普通正文中做无边界替换。"""

    if not text:
        return None
    if all(char in _CHINESE_DIGITS for char in text):
        return int("".join(str(_CHINESE_DIGITS[char]) for char in text))
    total = 0
    current = 0
    for char in text:
        if char in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[char]
        elif char in _CHINESE_SMALL_UNITS:
            total += (current or 1) * _CHINESE_SMALL_UNITS[char]
            current = 0
        else:
            return None
    return total + current


def _decimal_value(text: str) -> Decimal | None:
    """把阿拉伯数字或上下文中的中文数字转换为 Decimal。"""

    try:
        return Decimal(text)
    except InvalidOperation:
        value = _chinese_integer(text)
        return Decimal(value) if value is not None else None


def _decimal_text(value: Decimal) -> str:
    """输出稳定的非科学计数法数值键。"""

    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _modifier_key(value: str | None) -> str:
    """统一中英文约数与比较词。"""

    normalized = re.sub(r"\s+", " ", (value or "").strip().lower())
    if normalized in {"超过", "高于", "more than", "over", "above"}:
        return "gt"
    if normalized in {"低于", "少于", "不到", "less than", "under", "below"}:
        return "lt"
    if normalized in {"约", "大约", "近", "about", "approximately", "around"}:
        return "approx"
    return "eq"


def _ratio_key(modifier: str | None, value: Decimal) -> str:
    """比例约数与精确值按同一数值比较，方向性比较仍严格保留。"""

    relation = _modifier_key(modifier)
    if relation == "approx":
        relation = "eq"
    return f"ratio:{relation}:{_decimal_text(value)}"


def extract_quantity_mentions(text: str) -> list[QuantityMention]:
    """提取需要跨语言归一的数量表达，返回其原文跨度供裸数字阶段避让。"""

    mentions: list[QuantityMention] = []
    occupied: list[tuple[int, int]] = []

    def available(span: tuple[int, int]) -> bool:
        return not any(span[0] < end and span[1] > start for start, end in occupied)

    def add(key: str, display: str, span: tuple[int, int]) -> None:
        if not available(span):
            return
        # display 仅用于报告展示（数字遮蔽走 span）：正则的 \s* 会把
        # 表达式前后的空白带进 match.group(0)（如 " 15%"、"1.09 billion "），
        # 统一去除，避免报告与界面出现脏展示。
        mentions.append(QuantityMention(key=key, display=display.strip(), span=span))
        occupied.append(span)

    # 范围必须先于单月处理，否则“1-3月”只会识别末端的 3 月。
    for pattern, groups, language in (
        (_CHINESE_MONTH_RANGE, ("start", "end"), "zh"),
        (_ENGLISH_MONTH_RANGE, ("start", "end"), "en"),
    ):
        for match in pattern.finditer(text):
            for group in groups:
                raw = match.group(group)
                value = (
                    _decimal_value(raw)
                    if language == "zh"
                    else Decimal(_ENGLISH_MONTHS[raw.lower()])
                )
                if value is not None:
                    add(f"month:{_decimal_text(value)}", raw, match.span(group))

    for match in _CHINESE_MONTH.finditer(text):
        value = _decimal_value(match.group("month"))
        if value is not None:
            add(
                f"month:{_decimal_text(value)}",
                match.group(0),
                match.span(),
            )
    for match in _ENGLISH_MONTH_DATE.finditer(text):
        group = "leading" if match.group("leading") else "trailing"
        raw = match.group(group)
        add(f"month:{_ENGLISH_MONTHS[raw.lower()]}", raw, match.span(group))

    for pattern in (_CHINESE_SCALED_RANGE, _ENGLISH_SCALED_RANGE):
        for match in pattern.finditer(text):
            factor = _SCALE_FACTORS[match.group("scale").lower()]
            for group in ("start", "end"):
                value = _decimal_value(match.group(group))
                if value is not None:
                    add(
                        f"quantity:{_decimal_text(value * factor)}",
                        match.group(group),
                        match.span(group),
                    )

    for pattern in (_CHINESE_SCALED, _ENGLISH_SCALED):
        for match in pattern.finditer(text):
            value = _decimal_value(match.group("number"))
            if value is None:
                continue
            factor = _SCALE_FACTORS[match.group("scale").lower()]
            # 数字一致性只比较换算后的数值；币种名称由术语/文本规则负责，
            # 避免译文省略重复币种时把相同金额判成数字缺失。
            add(
                f"quantity:{_decimal_text(value * factor)}",
                match.group(0),
                match.span(),
            )

    ratio_patterns = (
        (_CHINESE_PERCENT, Decimal("1")),
        (_CHINESE_RATIO, Decimal("10")),
        (_NUMERIC_PERCENT, Decimal("1")),
    )
    for pattern, factor in ratio_patterns:
        for match in pattern.finditer(text):
            value = _decimal_value(match.group("number"))
            if value is None:
                continue
            add(
                _ratio_key(match.group("modifier"), value * factor),
                match.group(0),
                match.span(),
            )
    for pattern in (_CHINESE_HALF, _ENGLISH_HALF):
        for match in pattern.finditer(text):
            add(
                _ratio_key(match.group("modifier"), Decimal("50")),
                match.group(0),
                match.span(),
            )

    return sorted(mentions, key=lambda item: item.span)
