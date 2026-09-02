"""跨语言数量归一（quantities）的抽取级单元测试。

覆盖检测器级测试不便表达的守卫场景：货币锚定、缩写边界与
情态动词歧义，保证新归一化能力不把普通编号误判为金额。
"""

import unittest

from document_qa.detectors.quantities import extract_quantity_mentions


def quantity_keys(text: str) -> list[str]:
    """返回文本抽取出的数量键列表，便于断言。"""

    return [mention.key for mention in extract_quantity_mentions(text)]


class AbbreviatedScaledAmountTests(unittest.TestCase):
    """英文缩写倍率金额（$100M/$4.99B）的识别与守卫。"""

    def test_dollar_m_b_recognized(self) -> None:
        """$100M 与 $4.99B 应换算为绝对值数量。"""

        self.assertEqual(
            quantity_keys("Less than $100M and $1B - $4.99B."),
            [
                "quantity:100000000",
                "quantity:1000000000",
                "quantity:4990000000",
            ],
        )

    def test_currency_prefix_required(self) -> None:
        """无货币锚定的编号（Section 5B）不得判为金额。"""

        self.assertEqual(quantity_keys("See Section 5B for details."), [])

    def test_unit_suffix_letters_not_matched(self) -> None:
        """缩写后紧随字母（100MB 宽带）或数字时不应识别。"""

        self.assertEqual(quantity_keys("Speed upgraded to 100MB."), [])
        self.assertEqual(quantity_keys("Room 3B12 is closed."), [])

    def test_spelled_out_word_still_wins_after_abbrev_attempt(self) -> None:
        """$15 billion 全词表达不受缩写模式干扰，换算结果一致。"""

        self.assertEqual(
            quantity_keys("The deal closed at $15 billion."),
            ["quantity:15000000000"],
        )


class BareEnglishMonthTests(unittest.TestCase):
    """英文裸月份识别及其与中文"1月"的对 称性。"""

    def test_bare_capitalized_month_recognized(self) -> None:
        """in January（无日期相邻）应识别为 month:1。"""

        self.assertEqual(
            quantity_keys("We hosted a panel in January at the showcase."),
            ["month:1"],
        )

    def test_date_adjacent_month_not_double_counted(self) -> None:
        """January 13 只产生一条 month:1，不因裸月份模式双计。"""

        self.assertEqual(
            quantity_keys("Analysis as of January 13, 2025."),
            ["month:1"],
        )

    def test_may_is_never_a_bare_month(self) -> None:
        """情态动词 may（含句首大写）不得识别为五月。"""

        self.assertEqual(quantity_keys("Results may continue to improve."), [])
        self.assertEqual(quantity_keys("May continue as before."), [])

    def test_lowercase_verb_like_months_ignored(self) -> None:
        """小写动词化月份（march）不识别，避免普通动词误报。"""

        self.assertEqual(quantity_keys("Shares march higher."), [])


class MixedCardinalRangeTests(unittest.TestCase):
    """英文基数词与数字混排区间（six to 12 ↔ 6到12个月）的守恒。"""

    def test_word_digit_range_yields_bare_numbers(self) -> None:
        """six to 12 两侧都换算为裸数字键，与译文 6到12 守恒。"""

        self.assertEqual(
            quantity_keys("licensing deals may take six to 12 months."),
            ["6", "12"],
        )

    def test_sentence_initial_capitalized_word(self) -> None:
        """句首大写基数词（Six to 12）同样识别。"""

        self.assertEqual(
            quantity_keys("Six to 12 weeks are needed."),
            ["6", "12"],
        )

    def test_both_word_members_ignored(self) -> None:
        """纯基数词区间（one to one → 一对一）不识别，避免单侧缺失。"""

        self.assertEqual(quantity_keys("a one to one meeting"), [])

    def test_both_digit_members_left_to_existing_patterns(self) -> None:
        """两端都是数字的区间不在此处理，交由既有模式归一。"""

        self.assertEqual(
            quantity_keys("grew 1.5 to 2 billion yuan."),
            [
                "quantity:1500000000",
                "quantity:2000000000",
            ],
        )

    def test_percent_context_keeps_ratio_keys(self) -> None:
        """区间后随 percent 时让位百分比模式，数字端保持 ratio 键。"""

        self.assertEqual(
            quantity_keys("declined 20 to 30 percent."),
            ["ratio:eq:30"],
        )

    def test_pronoun_one_not_matched(self) -> None:
        """代词 one（no one / one of）后无数字端连接，不产生幻影数字。"""

        self.assertEqual(quantity_keys("one of the leading companies"), [])
        self.assertEqual(quantity_keys("no one to turn to"), [])


class PureMultiplierChainTests(unittest.TestCase):
    """中文纯乘数链单位声明（百万/千万）不作为数量参与守恒。"""

    def test_axis_unit_label_not_a_quantity(self) -> None:
        """交易总价值（百万美元）是 Y 轴单位声明，不产生数量键。"""

        self.assertEqual(quantity_keys("交易总价值（百万美元）"), [])

    def test_bare_multiplier_compounds_ignored(self) -> None:
        """十万/千万/百亿等纯乘数链一律不换算。"""

        self.assertEqual(quantity_keys("市场规模达千万级。"), [])
        self.assertEqual(quantity_keys("涉及金额十亿元。"), [])

    def test_counting_numeral_still_quantified(self) -> None:
        """含计数数字的三百万/十五亿仍是真实数量，照常换算。"""

        self.assertEqual(
            quantity_keys("斥资三百万美元收购。"),
            ["quantity:3000000"],
        )
        self.assertEqual(
            quantity_keys("估值十五亿美元。"),
            ["quantity:1500000000"],
        )

    def test_digit_prefixed_scaled_amount_unaffected(self) -> None:
        """数字前缀的常规倍率表达（430亿美元）行为不变。"""

        self.assertEqual(
            quantity_keys("以430亿美元收购Seagen。"),
            ["quantity:43000000000"],
        )


if __name__ == "__main__":
    unittest.main()
