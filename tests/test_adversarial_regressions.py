"""对抗性审查（2025-08）发现的缺陷回归测试。

每条用例对应一次真实缺陷（详见 docs/todo/tech-adoption-plan.md 落地记录），
防止修复被未来的改动悄悄退化。
"""

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from document_qa.detectors import ContentDetector
from document_qa.detectors.content import (
    _NUMBER_PATTERN,
    _normalize_number,
)
from document_qa.detectors.glossary import GlossaryDetector
from document_qa.glossary import Glossary, GlossaryEntry
from document_qa.grouping import RegionGrouper
from document_qa.matching import RegionMatcher
from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    ElementType,
    Page,
    Region,
)


def make_region(rid: str, text: str) -> Region:
    return Region(
        id=rid,
        page=1,
        type=ElementType.PARAGRAPH,
        bbox=BoundingBox(x=0, y=0, width=100, height=10),
        content=Content(text=text),
    )


def make_page(texts: list[str]) -> Page:
    return Page(
        document_id="d",
        page=1,
        width=500,
        height=800,
        regions=[make_region(f"r{i}", text) for i, text in enumerate(texts)],
    )


class NumberExtractionTests(unittest.TestCase):
    """对抗发现：千分位+小数被切断、前导零、全角数字。"""

    def test_thousands_with_decimal_stays_single_token(self) -> None:
        """1,137.5 必须抽为单个 1137.5，不得切成 1137 和 5。"""

        tokens = _NUMBER_PATTERN.findall("1,137.5 million")
        self.assertEqual([_normalize_number(t) for t in tokens], ["1137.5"])

    def test_date_zero_padding_equivalence(self) -> None:
        """2024-01-05 与 2024年1月5日 的数字集合必须等价。"""

        def extract(text: str) -> list[str]:
            return [
                _normalize_number(t) for t in _NUMBER_PATTERN.findall(text)
            ]

        self.assertEqual(extract("2024-01-05"), extract("2024年1月5日"))

    def test_fullwidth_digits_matched(self) -> None:
        """全角数字（中文排版）抽取后与半角等价。"""

        detector = ContentDetector()
        region = make_region("r", "共１２３项")
        self.assertEqual(detector._extract_numbers(region), {"123": 1})


class MixedLanguageTests(unittest.TestCase):
    """对抗发现：混排源页面产生整页漏译假阳性。"""

    def test_mixed_source_page_skipped(self) -> None:
        """源页面中英混排（投票平票）时漏译检测必须整体跳过。"""

        source = make_page(
            ["第一章 概述", "第二章 方法", "Chapter overview here.", "Methods."]
        )
        target = make_page(
            ["Chapter One Overview", "Chapter Two Methods", "The overview.", "Methods."]
        )
        issues = ContentDetector().detect(
            source, target, RegionMatcher().match_page(source, target)
        )
        self.assertEqual(
            [i for i in issues if i.type.value == "untranslated_text"], []
        )


class GlossaryBoundaryTests(unittest.TestCase):
    """对抗发现：术语子串误命中无关单词（AI 命中 said/raining）。"""

    def _detector(self) -> GlossaryDetector:
        return GlossaryDetector(
            Glossary(
                glossary_id="test-g",
                name="t",
                entries=[GlossaryEntry(term="AI", translations=["人工智能"])],
            )
        )

    def test_substring_word_not_matched(self) -> None:
        """said / raining 不得命中术语 AI。"""

        det = self._detector()
        self.assertFalse(det._contains("The said report", "AI", False))
        self.assertFalse(det._contains("It is raining", "AI", False))

    def test_standalone_term_matched(self) -> None:
        """独立出现的术语仍正常命中。"""

        self.assertTrue(self._detector()._contains("Uses AI models", "AI", False))

    def test_full_chain_no_false_positive(self) -> None:
        """源含 said、目标无 AI 内容时不得误报术语违规。"""

        source = make_page(["The said report."])
        target = make_page(["该报告。"])
        issues = self._detector().detect(
            source, target, RegionMatcher().match_page(source, target)
        )
        self.assertEqual(issues, [])

    def test_issue_ids_unique_per_region(self) -> None:
        """同页多区域同术语的 Issue ID 不得重复。"""

        source = make_page(["AI first.", "AI second."])
        target = make_page(["第一段。", "第二段。"])
        issues = self._detector().detect(
            source, target, RegionMatcher().match_page(source, target)
        )
        ids = [i.id for i in issues]
        self.assertEqual(len(ids), len(set(ids)))


class TableBlockTests(unittest.TestCase):
    """对抗发现：非 TEXT/IMAGE 组触发 max() 空序列崩溃。"""

    def test_table_block_grouped_without_crash(self) -> None:
        """TABLE Block 单独成组应产出 table 类型 Region 而非崩溃。"""

        block = Block(
            id="b1",
            page=1,
            type=ElementType.TABLE,
            bbox=BoundingBox(x=0, y=0, width=100, height=50),
            metadata={"source_block_index": 0},
        )
        page = Page(
            document_id="d", page=1, width=500, height=800, blocks=[block]
        )
        grouped = RegionGrouper().group_page(page)
        self.assertEqual(grouped.regions[0].type, ElementType.TABLE)


class HistoryConcurrencyTests(unittest.TestCase):
    """对抗发现：并发写历史记录时 record_id 碰撞导致静默丢失。"""

    def test_concurrent_adds_preserve_records(self) -> None:
        """并发写入不超过上限时，记录不得因 ID 碰撞丢失。"""

        from document_qa_server.services.history_service import (
            CompareHistoryService,
        )

        with TemporaryDirectory() as tmp:
            service = CompareHistoryService(
                artifacts_dir=Path(tmp), max_records=5
            )
            report = {
                "status": "pass",
                "document_score": 100.0,
                "summary": {"pages": 1, "issue_counts": {}},
                "rule_profile_reference": "x@1",
            }
            errors: list[str] = []

            def writer(i: int) -> None:
                try:
                    service.add(
                        report=report,
                        source_path="a.pdf",
                        target_path="b.pdf",
                        source_display=str(i),
                        target_display="b",
                    )
                except Exception as exc:  # pragma: no cover
                    errors.append(str(exc))

            threads = [
                threading.Thread(target=writer, args=(i,)) for i in range(20)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(len(service.list()), 5)


if __name__ == "__main__":
    unittest.main()
