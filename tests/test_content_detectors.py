"""内容级检测器（数字一致性、漏译）的单元测试。"""

import unittest

from document_qa.detectors import ContentDetector
from document_qa.matching import RegionMatcher
from document_qa.profiles import RuleProfile
from document_qa.schemas import (
    Block,
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


def make_raster_page(
    document_id: str,
    text: str,
    *,
    image_count: int = 8,
) -> Page:
    """构造含大面积未变化图像字形簇的跨语言页面。"""

    text_region = Region(
        id=f"{document_id}-text",
        page=1,
        type=ElementType.PARAGRAPH,
        bbox=BoundingBox(x=20, y=20, width=460, height=40),
        content=Content(text=text),
    )
    blocks = []
    regions = [text_region]
    for index in range(image_count):
        column = index % 4
        row = index // 4
        bbox = BoundingBox(
            x=50 + column * 100,
            y=200 + row * 40,
            width=40,
            height=40,
        )
        block_id = f"{document_id}-image-block-{index}"
        blocks.append(
            Block(
                id=block_id,
                page=1,
                type=ElementType.IMAGE,
                bbox=bbox,
                metadata={"content_sha256": f"glyph-{index}"},
            )
        )
        regions.append(
            Region(
                id=f"{document_id}-image-{index}",
                page=1,
                type=ElementType.IMAGE,
                bbox=bbox,
                children=[block_id],
            )
        )
    return Page(
        document_id=document_id,
        page=1,
        width=500,
        height=800,
        blocks=blocks,
        regions=regions,
    )


class NumberMismatchTests(unittest.TestCase):
    """验证页面级数字守恒检测。"""

    def test_reports_missing_number(self) -> None:
        """源中数字在目标页整体消失时必须报告。"""

        _, _, issues = detect_for(
            ["2024 年报告显示增长 15%。"], ["2024 年报告显示增长。"]
        )
        mismatches = [i for i in issues if i.type == IssueType.NUMBER_MISMATCH]
        self.assertEqual(len(mismatches), 1)
        # missing_numbers 存原文表达（含百分号）；历史登记失败"数字展示值"
        # 的根因是 display 带前导空格（" 15%"），strip 后应为 "15%"。
        self.assertEqual(mismatches[0].metrics["missing_numbers"], ["15%"])

    def test_unit_scale_error_description_shows_converted_values(self) -> None:
        """亿元误译为 billion 时，描述应附换算绝对值与 10 倍提示。

        回归背景：真实样例中 0.57亿元 被译为 0.57 billion yuan，原始
        表达式肉眼难辨差异，描述必须让复核者直接看到换算后的量级差。
        """

        _, _, issues = detect_for(
            ["预计2022年需求0.57亿元，至2025年达到28.36亿元。"],
            ["The 2022 demand is 0.57 billion yuan, reaching 2.836 billion yuan by 2025."],
        )
        mismatches = [i for i in issues if i.type == IssueType.NUMBER_MISMATCH]
        self.assertEqual(len(mismatches), 1)
        description = mismatches[0].description
        self.assertIn("0.57亿元 → 57,000,000", description)
        self.assertIn("0.57 billion yuan → 570,000,000", description)
        self.assertIn("两者换算后相差 10 倍，疑似单位换算错误", description)

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

    def test_chinese_month_name_matches_english_month(self) -> None:
        """中文数字月份与英文月份名称应归一为同一日期语义。"""

        _, _, issues = detect_for(
            ["报告日期：2024年一月5日。"],
            ["Report date: January 5, 2024."],
        )
        self.assertNotIn(IssueType.NUMBER_MISMATCH, [i.type for i in issues])

    def test_scaled_currency_equivalence(self) -> None:
        """亿与 billion 的倍率换算后金额相等，不应报告裸数字差异。"""

        _, _, issues = detect_for(
            ["积压订单达到310亿欧元。"],
            ["The backlog reached 31 billion euros."],
        )
        self.assertNotIn(IssueType.NUMBER_MISMATCH, [i.type for i in issues])

    def test_verbal_ratio_equivalence(self) -> None:
        """成数与英文比例表达应保留比较关系后再判断一致性。"""

        _, _, issues = detect_for(
            ["超过五成订单来自汽车产品。"],
            ["More than half of the orders were automotive products."],
        )
        self.assertNotIn(IssueType.NUMBER_MISMATCH, [i.type for i in issues])

    def test_scaled_range_equivalence(self) -> None:
        """带倍率的数量范围应分别换算上下界。"""

        _, _, issues = detect_for(
            ["预计市场规模为10至20亿元。"],
            ["The estimated market size is 1 to 2 billion yuan."],
        )
        self.assertNotIn(IssueType.NUMBER_MISMATCH, [i.type for i in issues])

    def test_ordinary_may_is_not_a_month(self) -> None:
        """普通情态动词 may 不得被误识别为五月。"""

        _, _, issues = detect_for(
            ["结果可能继续改善。"],
            ["Results may continue to improve."],
        )
        self.assertNotIn(IssueType.NUMBER_MISMATCH, [i.type for i in issues])

    def test_abbreviated_money_matches_chinese_scaled_amount(self) -> None:
        """英文财务缩写金额（$100M/$4.99B）与中文亿级译文应守恒。

        回归背景：真实记录 20260901-055449 第 1 页，图表分档
        "$100M - $499M" 被译为"1 亿 - 4.99 亿美元"，缩写 M/B 不被
        识别导致整页误报数字缺失+多余（21 处差异，severity high）。
        """

        _, _, issues = detect_for(
            [
                "Less than $100M and $1B - $4.99B and greater than $15B.",
                "The report is our 15th survey, presented in January at the showcase.",
            ],
            [
                "低于 1 亿美元和 10 亿 - 49.9 亿美元和超过 150 亿美元。",
                "本报告是第15份调查，于1月在展示会现场发布。",
            ],
        )
        self.assertNotIn(IssueType.NUMBER_MISMATCH, [i.type for i in issues])

    def test_number_mismatch_metrics_mark_page_scope(self) -> None:
        """页面级守恒 issue 应标注 comparison_scope，锚点文本不是译文对。"""

        _, _, issues = detect_for(
            ["2024 年报告显示增长 15%。"], ["2024 年报告显示增长。"]
        )
        mismatch = next(
            i for i in issues if i.type == IssueType.NUMBER_MISMATCH
        )
        self.assertEqual(mismatch.metrics["comparison_scope"], "page")


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

    def test_source_citation_with_kept_proper_noun_not_flagged(self) -> None:
        """来源行保留机构名（Syneos Health Consulting）不算漏译。

        回归背景：真实记录 20260901-065834 第 1/5/7 页，"来源：Syneos
        Health Consulting, Inc. 2025交易撮合者意向调查。N = 170。"是
        完整译文，机构名与统计记法按惯例保留拉丁原文，拉丁字母占比
        0.72 恰过 0.7 阈值被误报；占比应只统计剔除专名后的正文词。
        """

        _, _, issues = detect_for(
            ["Source: Syneos Health Consulting, Inc. Dealmakers' Intentions 2025. N = 170."],
            ["来源：Syneos Health Consulting, Inc. 2025交易撮合者意向调查。N = 170。"],
        )
        self.assertNotIn(
            IssueType.UNTRANSLATED_TEXT, [i.type for i in issues]
        )

    def test_untranslated_english_with_proper_nouns_still_flagged(self) -> None:
        """含专名的整段英文残留仍是漏译，专名豁免不得开漏洞。

        源为英文、目标页中文为主但该区域原样保留整段英文：剔除专名
        （Syneos Health Consulting）后正文仍是全英文，占比接近 1。
        """

        _, _, issues = detect_for(
            [
                "The survey explores what executives expect in terms of deals.",
                "Syneos Health Consulting surveyed 170 industry executives "
                "concerning licensing and acquisition deals.",
            ],
            [
                "本调查探讨了高管对交易的预期。",
                "Syneos Health Consulting surveyed 170 industry executives "
                "concerning licensing and acquisition deals.",
            ],
        )
        self.assertIn(
            IssueType.UNTRANSLATED_TEXT, [i.type for i in issues]
        )

    def test_detects_large_unchanged_raster_text_cluster(self) -> None:
        """跨语言页面的大面积未变化图像字形簇应聚合为一条漏译问题。"""

        source = make_raster_page("src", "这是需要翻译的中文页面内容。")
        target = make_raster_page(
            "tgt", "This page has otherwise been translated into English."
        )
        result = RegionMatcher().match_page(source, target)

        issues = ContentDetector().detect(source, target, result)
        raster_issues = [
            issue
            for issue in issues
            if issue.type == IssueType.UNTRANSLATED_RASTER
        ]

        self.assertEqual(len(raster_issues), 1)
        self.assertEqual(raster_issues[0].metrics["unchanged_image_count"], 8)

    def test_single_unchanged_image_is_not_raster_untranslated(self) -> None:
        """单张未变化照片或 Logo 不应被当作图像化文字漏译。"""

        source = make_raster_page(
            "src", "这是需要翻译的中文页面内容。", image_count=1
        )
        target = make_raster_page(
            "tgt",
            "This page has otherwise been translated into English.",
            image_count=1,
        )
        result = RegionMatcher().match_page(source, target)

        issues = ContentDetector().detect(source, target, result)

        self.assertNotIn(
            IssueType.UNTRANSLATED_RASTER, [issue.type for issue in issues]
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
