"""内容级检测器（数字一致性、漏译）的单元测试。"""

import unittest

from document_qa.detectors import ContentDetector
from document_qa.matching import RegionMatcher
from document_qa.profiles import RuleProfile
from document_qa.schemas import (
    BoundingBox,
    Content,
    ElementType,
    IssueType,
    Page,
    Region,
)


def make_page(document_id: str, page: int, texts: list[str]) -> Page:
    """按文本列表构造单页文档，Region 纵向排布。"""

    return Page(
        document_id=document_id,
        page=page,
        width=500,
        height=800,
        regions=[
            Region(
                id=f"{document_id}-r{index}",
                page=page,
                type=ElementType.PARAGRAPH,
                bbox=BoundingBox(x=20, y=20 + index * 40, width=400, height=30),
                content=Content(text=text),
            )
            for index, text in enumerate(texts)
        ],
    )


def detect_for(source_texts: list[str], target_texts: list[str]):
    """构造同页源/目标并返回 (页面, 匹配结果, Issue 列表)。"""

    source = make_page("src", 1, source_texts)
    target = make_page("tgt", 1, target_texts)
    result = RegionMatcher().match_page(source, target)
    return target, result, ContentDetector().detect(source, target, result)


class NumberMismatchTests(unittest.TestCase):
    """验证页面级数字守恒检测。"""

    def test_reports_missing_number(self) -> None:
        """源中数字在目标页整体消失时必须报告。"""

        _, _, issues = detect_for(
            ["2024 年报告显示增长 15%。"], ["2024 年报告显示增长。"]
        )
        mismatches = [i for i in issues if i.type == IssueType.NUMBER_MISMATCH]
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0].metrics["missing_numbers"], ["15"])

    def test_thousand_separator_equivalence(self) -> None:
        """千分位逗号差异不应判为数字错漏。"""

        _, _, issues = detect_for(
            ["总计 1,137 项。"], ["总计 1137 项。"]
        )
        self.assertNotIn(
            IssueType.NUMBER_MISMATCH, [i.type for i in issues]
        )

    def test_number_movement_between_regions_not_flagged(self) -> None:
        """数字在配对 Region 间移动（页面总量守恒）不应报告。"""

        _, _, issues = detect_for(
            ["2024 年预算", "覆盖 100 个城市"],
            ["预算年份 2024", "城市数量 100 个"],
        )
        self.assertNotIn(
            IssueType.NUMBER_MISMATCH, [i.type for i in issues]
        )


class UntranslatedTextTests(unittest.TestCase):
    """验证漏译检测的判定与豁免规则。"""

    def test_detects_english_left_in_chinese_target(self) -> None:
        """英译中场景：目标页主导语言为中文，但某段仍为英文时必须报告。"""

        source = make_page("src", 1, [
            "This paragraph was translated into Chinese correctly.",
            "Another paragraph about budgets follows here.",
        ])
        target = make_page("tgt", 1, [
            "这一段已经正确地翻译成了中文内容。",
            "This paragraph was NOT translated and stays English.",
        ])
        result = RegionMatcher().match_page(source, target)
        issues = ContentDetector().detect(source, target, result)
        self.assertIn(
            IssueType.UNTRANSLATED_TEXT, [i.type for i in issues]
        )

    def test_short_copyright_line_exempt(self) -> None:
        """版权行（© WHO）等短文本不判漏译。"""

        source = make_page("src", 1, ["Some translated content here."])
        target = make_page("tgt", 1, ["已翻译的正文内容。", "© WHO"])
        result = RegionMatcher().match_page(source, target)
        issues = ContentDetector().detect(source, target, result)
        self.assertNotIn(
            IssueType.UNTRANSLATED_TEXT, [i.type for i in issues]
        )

    def test_acronym_list_exempt(self) -> None:
        """机构缩写列表（UNICEF UNIDO）不判漏译。"""

        source = make_page("src", 1, ["Partner agencies listed below."])
        target = make_page("tgt", 1, ["合作伙伴机构如下。", "UNICEF UNIDO"])
        result = RegionMatcher().match_page(source, target)
        issues = ContentDetector().detect(source, target, result)
        self.assertNotIn(
            IssueType.UNTRANSLATED_TEXT, [i.type for i in issues]
        )

    def test_same_language_documents_skipped(self) -> None:
        """源与目标同为中文时漏译检测整体跳过。"""

        _, result, issues = detect_for(
            ["这是中文原文。"], ["这是中文目标。"]
        )
        self.assertNotIn(
            IssueType.UNTRANSLATED_TEXT, [i.type for i in issues]
        )


class ProfileToggleTests(unittest.TestCase):
    """验证配置开关可以关闭内容检测。"""

    def test_toggles_disable_content_detectors(self) -> None:
        """关闭开关后数字差异与英文残留均不再报告。"""

        profile = RuleProfile(
            profile_id="content-off",
            name="content-off",
            detectors={"enabled": {"number_mismatch": False, "untranslated_text": False}},
        )
        source = make_page("src", 1, ["Growth reached 15% in 2024."])
        target = make_page("tgt", 1, ["Growth reached 15% in 2024."])
        result = RegionMatcher().match_page(source, target)
        issues = ContentDetector(profile).detect(source, target, result)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
