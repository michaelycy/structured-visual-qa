"""术语合规检测：目标文本中的术语译法必须命中术语库允许集合。

检测逻辑分两层：
1. 源区域出现术语 → 对应目标区域必须出现任一允许译法（漏译术语）；
2. 目标区域出现术语的其他译法变体无法穷举，只做第 1 层的正向检查。
违规输出统一 Issue（glossary 检测器），阈值/开关不涉及（术语规则本身
就是二值判定），因此不进 RuleProfile。
"""

from __future__ import annotations

import re

from document_qa.glossary import Glossary
from document_qa.detectors.evidence import region_evidence
from document_qa.schemas import (
    Issue,
    IssueType,
    Page,
    PageMatchResult,
    Region,
    Severity,
    TEXT_TYPES,
)


def _compile_pattern(needle: str, case_sensitive: bool) -> re.Pattern[str] | None:
    """把术语编译成查找模式；纯 CJK 术语返回 None（用子串判断）。

    拉丁术语用词边界正则避免短术语命中无关单词（AI 命中 said/raining）；
    中文没有词边界标记，术语可自然嵌入复合词，保持子串匹配。
    """

    if not any("a" <= ch.lower() <= "z" for ch in needle):
        return None
    return re.compile(
        r"\b" + re.escape(needle) + r"\b",
        0 if case_sensitive else re.IGNORECASE,
    )


def _pattern_hit(pattern: re.Pattern[str] | None, text: str, needle: str) -> bool:
    """按预编译模式判断 text 是否命中 needle；None 表示纯 CJK 子串判断。"""

    if pattern is None:
        return needle in text
    return bool(pattern.search(text))


class GlossaryDetector:
    """检查配对区域之间的术语译法合规性。"""

    def __init__(self, glossary: Glossary) -> None:
        """注入版本化术语库；引用随报告快照保证可复现。"""

        self.glossary = glossary
        # 预编译每条术语与允许译法的查找模式，避免在每对区域上重复
        # re.compile（大术语库下的热点）。纯 CJK 术语返回 None，沿用子串判断。
        self._prepared = [
            (
                entry,
                _compile_pattern(entry.term, entry.case_sensitive),
                [
                    _compile_pattern(translation, entry.case_sensitive)
                    for translation in entry.translations
                ],
            )
            for entry in glossary.entries
        ]

    def detect(
        self, source: Page, target: Page, result: PageMatchResult
    ) -> list[Issue]:
        """对每对匹配区域执行术语正向检查。"""

        source_regions = {region.id: region for region in source.regions}
        target_regions = {region.id: region for region in target.regions}
        issues: list[Issue] = []
        for match in result.matches:
            source_region = source_regions.get(match.source_region_id)
            target_region = target_regions.get(match.target_region_id)
            if source_region is None or target_region is None:
                continue
            if target_region.type not in TEXT_TYPES:
                continue
            issues.extend(
                self._check_pair(source_region, target_region, target.page)
            )
        return issues

    def _check_pair(
        self, source_region: Region, target_region: Region, page_number: int
    ) -> list[Issue]:
        """源区域出现的每个术语，在目标区域中查找允许译法。"""

        source_text = (
            source_region.content.text if source_region.content else ""
        ) or ""
        target_text = (
            target_region.content.text if target_region.content else ""
        ) or ""
        issues: list[Issue] = []
        for entry, term_pattern, translation_patterns in self._prepared:
            if not _pattern_hit(term_pattern, source_text, entry.term):
                continue
            # 命中任一允许译法即合规。
            if any(
                _pattern_hit(pattern, target_text, translation)
                for pattern, translation in zip(translation_patterns, entry.translations)
            ):
                continue
            issues.append(
                Issue(
                    # 含目标区域 ID 防止同页多配对同术语时的 ID 冲突。
                    id=f"p{page_number}-glossary-{target_region.id}-{entry.term[:20]}",
                    page=page_number,
                    type=IssueType.GLOSSARY_VIOLATION,
                    severity=Severity.HIGH,
                    source_region=source_region.id,
                    target_region=target_region.id,
                    bbox=target_region.bbox,
                    metrics={
                        "term": entry.term,
                        "allowed_translations": entry.translations,
                        "note": entry.note,
                        "glossary_reference": self.glossary.reference,
                        **region_evidence(source_region, target_region),
                    },
                    description=(
                        f"术语「{entry.term}」未使用指定译法"
                        f"（{', '.join(entry.translations)}）。"
                    ),
                    detector="glossary",
                )
            )
        return issues

    @staticmethod
    def _contains(text: str, needle: str, case_sensitive: bool) -> bool:
        """大小写可配置的包含判断；保留公开签名供测试与调用方使用。

        纯子串会让短术语（AI）命中无关单词（said/rain/maintain）；
        含拉丁字母的术语改用词边界正则，纯 CJK 术语保持子串
        （中文没有词边界标记，术语可自然嵌入复合词）。
        """

        return _pattern_hit(_compile_pattern(needle, case_sensitive), text, needle)
