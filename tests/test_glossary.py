"""术语库与术语合规检测的单元测试。"""

import unittest

from document_qa.detectors import RuleDetector  # noqa: F401 保持导入一致性
from document_qa.detectors.glossary import GlossaryDetector
from document_qa.glossary import Glossary, GlossaryEntry, default_glossary
from document_qa.matching import RegionMatcher
from document_qa.schemas import (
    BoundingBox,
    Content,
    ElementType,
    IssueType,
    Page,
    Region,
)


def make_page(document_id: str, page: int, texts: list[str]) -> Page:
    """按文本列表构造单页文档。"""

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


GLOSSARY = Glossary(
    glossary_id="test",
    name="测试术语库",
    entries=[
        GlossaryEntry(term="United Nations", translations=["联合国"]),
        GlossaryEntry(
            term="gross domestic product",
            translations=["国内生产总值", "GDP"],
        ),
    ],
)


class GlossaryModelTests(unittest.TestCase):
    """验证术语库 Schema 校验。"""

    def test_rejects_duplicated_terms(self) -> None:
        """重复术语必须校验失败。"""

        with self.assertRaises(ValueError):
            Glossary(
                glossary_id="dup",
                name="重复",
                entries=[
                    GlossaryEntry(term="AI", translations=["人工智能"]),
                    GlossaryEntry(term="AI", translations=["AI 技术"]),
                ],
            )

    def test_reference_format(self) -> None:
        """版本引用格式为 id@version。"""

        self.assertEqual(GLOSSARY.reference, "test@1")

    def test_default_glossary_valid(self) -> None:
        """内置示例术语库通过校验。"""

        self.assertGreater(len(default_glossary().entries), 0)


class GlossaryDetectorTests(unittest.TestCase):
    """验证术语合规检测行为。"""

    def _detect(self, source_texts: list[str], target_texts: list[str]):
        source = make_page("src", 1, source_texts)
        target = make_page("tgt", 1, target_texts)
        result = RegionMatcher().match_page(source, target)
        return GlossaryDetector(GLOSSARY).detect(source, target, result)

    def test_reports_wrong_translation(self) -> None:
        """源含术语而目标未用指定译法时必须报告。"""

        issues = self._detect(
            ["The United Nations published a report."],
            ["联合国发布了一份报告。"],
        )
        self.assertEqual(issues, [])

    def test_flags_missing_term_translation(self) -> None:
        """目标缺失术语译法（写成其他说法）必须报告。"""

        issues = self._detect(
            ["The United Nations published a report."],
            ["国际联合组织发布了一份报告。"],
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].type, IssueType.GLOSSARY_VIOLATION)
        self.assertEqual(issues[0].metrics["term"], "United Nations")

    def test_multiple_allowed_translations(self) -> None:
        """多个允许译法任一命中即合规。"""

        self.assertEqual(
            self._detect(
                ["Gross domestic product grew."],
                ["国内生产总值增长。"],
            ),
            [],
        )
        self.assertEqual(
            self._detect(
                ["Gross domestic product grew."],
                ["GDP 增长。"],
            ),
            [],
        )

    def test_case_insensitive_by_default(self) -> None:
        """默认大小写不敏感：源术语大小写漂移仍应命中。"""

        issues = self._detect(
            ["the united nations published a report."],
            ["国际联合组织发布了一份报告。"],
        )
        self.assertEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
