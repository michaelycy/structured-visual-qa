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
# 英文裸月份（in January at ...）：中文"1月"无需邻接日期即被识别为
# 月份，英文若只认"月份名+日期数字"（January 13），同一处时间状语
# 在两侧计数不对称，页面级守恒会误报"多余 1月"。仅识别首字母大写
# 的月份名，避免小写动词误报（stocks march higher）；may 作情态动词
# 的频率远高于月份语义，整体排除（May 13 已由日期相邻模式覆盖）。
_BARE_MONTH_NAMES = "|".join(
    name.capitalize() for name in _ENGLISH_MONTHS if name != "may"
)
_ENGLISH_MONTH_BARE = re.compile(rf"\b(?P<month>{_BARE_MONTH_NAMES})\b")
_CHINESE_MONTH_RANGE = re.compile(
    rf"(?P<start>{_DECIMAL_OR_CHINESE})\s*(?:-|—|–|至|到)\s*"
    rf"(?P<end>{_DECIMAL_OR_CHINESE})\s*月"
)
_CHINESE_MONTH = re.compile(rf"(?P<month>{_DECIMAL_OR_CHINESE})\s*月")

_CHINESE_SCALED = re.compile(
    rf"(?P<number>{_DECIMAL_OR_CHINESE})\s*(?P<scale>万|亿)\s*"
    r"(?P<currency>人民币|元|美元|美金|欧元)?"
)
# 纯乘数链（十万/百万/千万/百亿……）不含任何计数数字，是坐标轴与
# 表头的「单位声明」写法：译文"交易总价值（百万美元）"对应源文
# "Total Value of Deals (USD $M)"，英文侧 in millions/$M 因不含数字
# 本来就不抽取，中文侧若把"百万"换算成 1,000,000 必然制造单侧多余
# （真实记录 20260901-073417 第 2 页误报的根因）。含计数数字的表达
# （三百万、十五亿）仍是真实数量，照常换算。
_PURE_MULTIPLIER_CHAIN = re.compile(r"[十百千]+")
_CHINESE_SCALED_RANGE = re.compile(
    rf"(?P<start>{_DECIMAL_OR_CHINESE})\s*(?:-|—|–|至|到)\s*"
    rf"(?P<end>{_DECIMAL_OR_CHINESE})\s*(?P<scale>万|亿)\s*"
    r"(?P<currency>人民币|元|美元|美金|欧元)?"
)
# 英文财务缩写金额（$100M、$4.99B、€5m）：图表分档与坐标轴的惯用
# 写法，中文译文会展开为"1 亿 / 4.99 亿美元"，语义完全等价；只识别
# thousand/million/billion 全词时这些表达会降级为裸数字，与中文侧的
# 倍率数量守恒必然错位（真实记录 20260901-055449 第 1 页整页误报的
# 根因）。必须锚定货币前缀，防止把 "Section 5B" 这类编号误判成金额；
# 单字母后紧随字母或数字的组合（100MB）同样不成立。
_ENGLISH_ABBR_SCALED = re.compile(
    r"(?:US\$|C\$|A\$|HK\$|NT\$|S\$|[$€£¥₹]|USD|EUR|GBP|JPY|CNY|RMB|CHF|CAD|AUD)\s*"
    r"(?P<number>\d+(?:\.\d+)?)\s*(?P<scale>[MBK])(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_ENGLISH_SCALED = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*"
    r"(?P<scale>thousand|million|billion)\s*"
    r"(?P<currency>rmb|yuan|cny|usd|us dollars?|dollars?|euros?|eur)?\b",
    re.IGNORECASE,
)
# 缩写单字母到全词倍率键的映射，复用 _SCALE_FACTORS 倍率表。
_ABBR_SCALE_WORDS = {"k": "thousand", "m": "million", "b": "billion"}
# 英文基数词表：只收数值含义明确的整数词，不收 hundred/thousand
# （冠词歧义：a hundred）。报告类译文对数据区间一律数字化
# （six to 12 months → 6到12个月），源文"基数词+数字"混写是明确的
# 数值区间信号；只认阿拉伯数字会让源侧整体缺号（同上记录第 2 页
# "多余 6" 误报的根因）。
_ENGLISH_CARDINALS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_CARDINAL_WORDS = "|".join(_ENGLISH_CARDINALS)
# 基数词与数字混排区间（six to 12）：两端换算为裸数字键，与译文侧
# 裸数字守恒。两端同类（1.5 to 2、one to one）不在此处理：前者由
# 裸数字与既有倍率/百分比模式覆盖，抢占其跨度会破坏 ratio 键归一；
# 后者（one to one → 一对一）译文通常不含数字，识别反而制造缺失。
_ENGLISH_CARDINAL_RANGE = re.compile(
    rf"\b(?P<start>{_CARDINAL_WORDS}|\d+(?:\.\d+)?)\s*"
    r"(?:-|—|–|to|through)\s*"
    rf"(?P<end>\d+(?:\.\d+)?|{_CARDINAL_WORDS})\b",
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
    # 裸月份只补位未被日期相邻模式占用的跨度，避免同一处月份双计。
    for match in _ENGLISH_MONTH_BARE.finditer(text):
        raw = match.group("month")
        add(f"month:{_ENGLISH_MONTHS[raw.lower()]}", raw, match.span())

    for pattern in (_CHINESE_SCALED_RANGE, _ENGLISH_SCALED_RANGE):
        for match in pattern.finditer(text):
            factor = _SCALE_FACTORS[match.group("scale").lower()]
            for group in ("start", "end"):
                raw = match.group(group)
                value = _decimal_value(raw)
                # 纯乘数链端（百万到千万这类单位声明）不是数量，跳过。
                if value is None or _PURE_MULTIPLIER_CHAIN.fullmatch(raw):
                    continue
                add(
                    f"quantity:{_decimal_text(value * factor)}",
                    raw,
                    match.span(group),
                )

    for pattern in (_CHINESE_SCALED, _ENGLISH_ABBR_SCALED, _ENGLISH_SCALED):
        for match in pattern.finditer(text):
            raw = match.group("number")
            value = _decimal_value(raw)
            if value is None or _PURE_MULTIPLIER_CHAIN.fullmatch(raw):
                continue
            scale = match.group("scale").lower()
            # 缩写单字母（k/m/b）先归一到全词，再查同一张倍率表。
            factor = _SCALE_FACTORS[_ABBR_SCALE_WORDS.get(scale, scale)]
            # 数字一致性只比较换算后的数值；币种名称由术语/文本规则负责，
            # 避免译文省略重复币种时把相同金额判成数字缺失。
            add(
                f"quantity:{_decimal_text(value * factor)}",
                match.group(0),
                match.span(),
            )

    # 混排区间（six to 12 months ↔ 6到12个月）：基数词端换算为裸数字
    # 键。放在倍率区间之后运行，"1.5 to 2 billion" 的端点已由倍率
    # 区间占用，不会被这里降级成裸数字。
    for match in _ENGLISH_CARDINAL_RANGE.finditer(text):
        # 百分比上下文交还百分比模式：数字端须保持 ratio 键，混入
        # 裸数字键会与译文侧（20%到30%）失配。
        if re.match(r"\s*(?:%|percent\b)", text[match.end():], re.IGNORECASE):
            continue
        start_raw = match.group("start")
        end_raw = match.group("end")
        start_digit = start_raw[0].isdigit()
        end_digit = end_raw[0].isdigit()
        # 仅"一端数字、一端基数词"的混排区间才处理；两端同类交给
        # 既有模式或直接忽略（见 _ENGLISH_CARDINAL_RANGE 注释）。
        if start_digit == end_digit:
            continue
        for group, is_digit in (("start", start_digit), ("end", end_digit)):
            raw = match.group(group)
            value = (
                Decimal(raw)
                if is_digit
                else Decimal(_ENGLISH_CARDINALS[raw.lower()])
            )
            add(_decimal_text(value), raw, match.span(group))

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
