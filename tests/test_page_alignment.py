import unittest

from document_qa.matching import PageAligner
from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import (
    BoundingBox,
    Document,
    ElementType,
    Page,
    Region,
)


def make_document(
    document_id: str, *, start_page: int, page_count: int
) -> Document:
    """构造版面指纹独特且逐页稳定的文档，用于隔离测试页对齐。"""

    pages = []
    for offset in range(page_count):
        page_number = start_page + offset
        pages.append(
            Page(
                document_id=document_id,
                page=page_number,
                width=200,
                height=200,
                regions=[
                    Region(
                        id=f"{document_id}-p{page_number}-text",
                        page=page_number,
                        type=ElementType.PARAGRAPH,
                        bbox=BoundingBox(
                            x=10 + offset * 15, y=10, width=100, height=20
                        ),
                    ),
                    Region(
                        id=f"{document_id}-p{page_number}-image",
                        page=page_number,
                        type=ElementType.IMAGE,
                        bbox=BoundingBox(x=10, y=80, width=80, height=60),
                    ),
                ],
            )
        )
    return Document(
        document_id=document_id,
        source_path=f"{document_id}.pdf",
        pages=pages,
    )


class PageAlignerTests(unittest.TestCase):
    """验证跨页对齐在移页、缺页和直配场景下的行为。"""

    def test_identity_when_pages_match_one_to_one(self) -> None:
        """页面一一对应时必须保持按页码直配。"""

        source = make_document("source", start_page=1, page_count=4)
        target = make_document("target", start_page=1, page_count=4)

        alignment = PageAligner().align(source, target)

        self.assertEqual(
            alignment.pairs, [(1, 1), (2, 2), (3, 3), (4, 4)]
        )
        self.assertEqual(alignment.missing_source_pages, [])
        self.assertEqual(alignment.extra_target_pages, [])

    def test_detects_shifted_target_pages(self) -> None:
        """目标文档整体后移一页时，应恢复移位对齐而不是逐页误判偏移。"""

        source = make_document("source", start_page=1, page_count=4)
        target = make_document("target", start_page=2, page_count=4)

        alignment = PageAligner().align(source, target)

        self.assertEqual(alignment.pairs, [(1, 2), (2, 3), (3, 4), (4, 5)])
        self.assertEqual(alignment.missing_source_pages, [])
        self.assertEqual(alignment.extra_target_pages, [])

    def test_detects_missing_source_page_under_shift(self) -> None:
        """目标少一页导致整体前移时，应找回对应关系并标记缺失页。"""

        source = make_document("source", start_page=1, page_count=4)
        # 目标从第 2 页开始且只有 3 页：源第 1-3 页对应目标第 2-4 页，
        # 源第 4 页在目标中缺失。
        target = make_document("target", start_page=2, page_count=3)

        alignment = PageAligner().align(source, target)

        self.assertEqual(alignment.pairs, [(1, 2), (2, 3), (3, 4)])
        self.assertEqual(alignment.missing_source_pages, [4])
        self.assertEqual(alignment.extra_target_pages, [])

    def test_alignment_can_be_disabled(self) -> None:
        """关闭对齐时退回按页码直配并标记差集页面。"""

        profile = RuleProfile(
            profile_id="no-align",
            name="no-align",
            alignment={"enabled": False},
        )
        source = make_document("source", start_page=1, page_count=3)
        target = make_document("target", start_page=2, page_count=3)

        alignment = PageAligner(profile).align(source, target)

        self.assertEqual(alignment.pairs, [(2, 2), (3, 3)])
        self.assertEqual(alignment.missing_source_pages, [1])
        self.assertEqual(alignment.extra_target_pages, [4])

    def test_default_profile_alignment_settings(self) -> None:
        """内置配置默认启用跨页对齐。"""

        self.assertTrue(default_rule_profile().alignment.enabled)


if __name__ == "__main__":
    unittest.main()
