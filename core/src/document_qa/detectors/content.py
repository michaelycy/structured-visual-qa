"""内容级确定性检测：数字一致性与漏译（未翻译）。

与布局检测同构：消费 Matcher 的配对结果 + Region 文本内容，输出统一
Issue。不使用任何模型或外部服务，跨语言判断基于确定性字符集规则。
"""

from __future__ import annotations

import re
from collections import Counter

from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import Issue, IssueType, Page, PageMatchResult, Region, Severity, TEXT_TYPES

# 数字抽取：整数、千分位、小数的完整组合。千分位必须恰好 3 位且后随
# 数字边界（1,137.5 抽为单个 1137.5），避免把小数点后的部分切成独立 token。
_NUMBER_PATTERN = re.compile(r"\d+(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
# 全角数字常见于中文排版，先归一化为半角再抽取。
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９．，", "0123456789.,")
# 判定为"源语言文字"的 Unicode 区块；中英互译场景覆盖 CJK 与拉丁字母。
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")
# 全大写字母词（机构缩写：UNICEF、WHO、CSAM）通常保留原文不翻译。
_ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,}\b")


def _normalize_number(token: str) -> str:
    """归一化数字 token：去千分位逗号 + 去前导零（日期/页码场景）。"""

    token = token.replace(",", "")
    if "." in token:
        whole, _, fraction = token.partition(".")
        return f"{whole.lstrip('0') or '0'}.{fraction}"
    return token.lstrip("0") or "0"


class ContentDetector:
    """检查配对区域之间的数字一致性与目标文本的翻译完整性。"""

    def __init__(self, profile: RuleProfile | None = None) -> None:
        """初始化带版本的检测开关和阈值。"""

        self.profile = profile or default_rule_profile()

    def detect(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """按固定顺序运行内容规则，保证报告输出稳定。"""

        issues: list[Issue] = []
        enabled = self.profile.detectors.enabled
        if enabled.number_mismatch:
            issues.extend(self._detect_number_mismatch(source, target, result))
        if enabled.untranslated_text:
            issues.extend(self._detect_untranslated(source, target, result))
        return issues

    def _detect_number_mismatch(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """页面级数字集合守恒检查：总量不一致才报告，附差集明细。

        翻译中数字位置常在配对 Region 间移动（页眉日期 vs 正文年份），
        逐对比较会误报互换；页面级守恒只捕获真实的错漏译。
        """

        source_numbers = Counter()
        target_numbers = Counter()
        for region in source.regions:
            source_numbers += self._extract_numbers(region)
        for region in target.regions:
            target_numbers += self._extract_numbers(region)
        if not source_numbers and not target_numbers:
            return []
        missing = source_numbers - target_numbers
        extra = target_numbers - source_numbers
        if not missing and not extra:
            return []
        # 定位必须在目标侧：契约要求 Issue 的 bbox 为 Target BBox，
        # 前端红框画在目标页渲染图上，拿源区域坐标会指到错误位置。
        # 优先找包含多余数字的目标区域（错译的数字就在那里）；
        # 只有缺失时，把含缺失数字的源区域经匹配结果映射到对应目标区域。
        extra_anchor = self._find_number_anchor(target, extra)
        source_anchor = self._find_number_anchor(source, missing)
        target_region = extra_anchor or self._map_to_target(
            source_anchor, target, result
        )
        # 差异明细直接写进描述，界面列表不展开也能看到具体数字。
        detail_parts = []
        if missing:
            detail_parts.append(
                "缺失数字：" + "、".join(sorted(missing.elements()))
            )
        if extra:
            detail_parts.append(
                "多余数字：" + "、".join(sorted(extra.elements()))
            )
        return [
            Issue(
                id=f"p{target.page}-numbers",
                page=target.page,
                type=IssueType.NUMBER_MISMATCH,
                severity=Severity.HIGH,
                source_region=source_anchor.id if source_anchor else None,
                target_region=target_region.id if target_region else None,
                bbox=target_region.bbox if target_region else None,
                metrics={
                    "source_numbers": sorted(source_numbers.elements()),
                    "target_numbers": sorted(target_numbers.elements()),
                    "missing_numbers": sorted(missing.elements()),
                    "extra_numbers": sorted(extra.elements()),
                },
                description=(
                    "目标页面数字与源页面不一致，可能存在错漏译。"
                    + "（" + "；".join(detail_parts) + "）"
                ),
                detector="content-numbers",
            )
        ]

    @staticmethod
    def _find_number_anchor(
        page: Page, numbers: Counter
    ) -> Region | None:
        """找到包含指定数字集合的区域，用于问题定位。"""

        for region in page.regions:
            if ContentDetector._extract_numbers(region) & numbers:
                return region
        return None

    @staticmethod
    def _map_to_target(
        source_region: Region | None,
        target: Page,
        result: PageMatchResult,
    ) -> Region | None:
        """把源锚点区域经匹配结果映射为目标区域（缺失数字只存在于源侧）。

        返回 None 表示该源区域未匹配（如目标侧整块缺失），
        此时 Issue 不带 bbox，退化为页面级提示。
        """

        if source_region is None:
            return None
        target_ids = {
            match.target_region_id
            for match in result.matches
            if match.source_region_id == source_region.id
        }
        for region in target.regions:
            if region.id in target_ids:
                return region
        return None

    def _detect_untranslated(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """目标文本框仍大量保留源语言文字时判为漏译。

        判据是"源语言为主、目标语言占比极低"：以源页面主导语言为参照，
        目标区域中源语言字符占比超过阈值且目标语言字符近乎为零。
        """

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        source_language = self._dominant_language(
            [region for region in source_regions.values()]
        )
        target_language = self._dominant_language(
            list(target_regions.values())
        )
        if (
            source_language == target_language
            or source_language is None
            or source_language == "mixed"
        ):
            # 双语同文、源语言无法判定、或源页面本身混排（中英对照的
            # 目录/封面页）时跳过——混排源无法定义"未翻译"参照，
            # 强行判定会产生整页假阳性。
            return []
        issues: list[Issue] = []
        threshold = self.profile.detectors.thresholds.untranslated_ratio
        min_letters = self.profile.detectors.thresholds.untranslated_min_letters
        for match in result.matches:
            source_region = source_regions.get(match.source_region_id)
            target_region = target_regions.get(match.target_region_id)
            if source_region is None or target_region is None:
                continue
            if target_region.type not in TEXT_TYPES:
                continue
            text = target_region.content.text if target_region.content else None
            if not text:
                continue
            # 机构名、版权行（© WHO、© UNFPA）本来就保留原文；
            # 字母字符过少或全由大写缩写构成的短文本不参与漏译判定。
            letters = _CJK_PATTERN.findall(text) + _LATIN_PATTERN.findall(text)
            if len(letters) < min_letters:
                continue
            without_acronyms = _ACRONYM_PATTERN.sub("", text)
            remaining = (
                _CJK_PATTERN.findall(without_acronyms)
                + _LATIN_PATTERN.findall(without_acronyms)
            )
            if len(remaining) < min_letters:
                continue
            ratio = self._language_ratio(text, source_language)
            if ratio >= threshold:
                issues.append(
                    Issue(
                        id=f"p{target.page}-untranslated-{target_region.id}",
                        page=target.page,
                        type=IssueType.UNTRANSLATED_TEXT,
                        severity=Severity.HIGH,
                        source_region=source_region.id,
                        target_region=target_region.id,
                        bbox=target_region.bbox,
                        metrics={
                            "source_language_ratio": round(ratio, 3),
                            "threshold": threshold,
                            "sample": text[:60],
                        },
                        description="目标文本区仍保留源语言内容，疑似漏译。",
                        detector="content-untranslated",
                    )
                )
        return issues

    @staticmethod
    def _extract_numbers(region: Region) -> Counter:
        """抽取区域文本中的数字（千分位归一化：1,137 与 1137 等价）。

        中文排版常去掉千分位逗号，格式差异不应判为数字错漏；
        全角数字先归一；前导零去除以对齐日期类写法（01-05 与 1-5）。
        """

        text = region.content.text if region.content else None
        if not text:
            return Counter()
        normalized = text.translate(_FULLWIDTH_DIGITS)
        return Counter(
            _normalize_number(token) for token in _NUMBER_PATTERN.findall(normalized)
        )

    @staticmethod
    def _dominant_language(regions: list[Region]) -> str | None:
        """按各 Region 主语言的数量投票判断页面主导语言。

        用区域数而非字符数投票：英文单词字母多、中文汉字信息密度高，
        按字符数统计会把"中文为主夹一段英文"的页面误判为英文。
        """

        votes: Counter = Counter()
        for region in regions:
            # 图片等 Region 的 content.text 可能为 None，需先判空。
            text = region.content.text if region.content else ""
            if not text:
                continue
            cjk = len(_CJK_PATTERN.findall(text))
            latin = len(_LATIN_PATTERN.findall(text))
            if cjk == 0 and latin == 0:
                continue
            if cjk > latin:
                votes["cjk"] += 1
            elif latin > cjk:
                votes["latin"] += 1
        if not votes:
            return None
        top = votes.most_common(2)
        # 平票视为混排，无法定义"源语言"，漏译判定跳过。
        if len(top) == 2 and top[0][1] == top[1][1]:
            return "mixed"
        return top[0][0]

    @staticmethod
    def _language_ratio(text: str, language: str) -> float:
        """计算文本中指定语言字母（排除数字与标点）的占比。"""

        pattern = _CJK_PATTERN if language == "cjk" else _LATIN_PATTERN
        letters = _CJK_PATTERN.findall(text) + _LATIN_PATTERN.findall(text)
        if not letters:
            return 0.0
        return len(pattern.findall(text)) / len(letters)
