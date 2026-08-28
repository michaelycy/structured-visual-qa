"""图片内部 OCR 漏译检测的阳性与边界用例。"""

import unittest

from document_qa.detectors.raster_ocr import RasterOCRDetector
from document_qa.matching import RegionMatcher
from document_qa.ocr import OCRLine, OCRResult
from document_qa.schemas import (
    Block,
    BoundingBox,
    Content,
    ElementType,
    IssueType,
    Page,
    Region,
)


class FakeOCRProvider:
    """按调用顺序返回源图、译图结果的内存 OCR Stub。"""

    provider_name = "fake"
    model_fingerprint = "fake-v1"

    def __init__(self, target_text: str) -> None:
        self.target_text = target_text
        self.calls = 0

    def recognize(self, image_png: bytes) -> OCRResult:
        """第一次返回中文源图，第二次返回测试指定的译图文字。"""

        text = "功率模块供应链结构" if self.calls == 0 else self.target_text
        self.calls += 1
        return OCRResult(
            image_width=300,
            image_height=200,
            lines=[
                OCRLine(
                    text=text,
                    confidence=0.95,
                    bbox=BoundingBox(x=20, y=20, width=240, height=40),
                )
            ],
        )


def make_page(document_id: str, text: str, digest: str) -> Page:
    """构造一个含正常正文和单张大图的页面。"""

    image_bbox = BoundingBox(x=40, y=120, width=220, height=140)
    image_block_id = f"{document_id}-image-block"
    return Page(
        document_id=document_id,
        page=1,
        width=300,
        height=300,
        blocks=[
            Block(
                id=image_block_id,
                page=1,
                type=ElementType.IMAGE,
                bbox=image_bbox,
                metadata={"content_sha256": digest},
            )
        ],
        regions=[
            Region(
                id=f"{document_id}-text",
                page=1,
                type=ElementType.PARAGRAPH,
                bbox=BoundingBox(x=20, y=20, width=260, height=50),
                content=Content(text=text),
            ),
            Region(
                id=f"{document_id}-image",
                page=1,
                type=ElementType.IMAGE,
                bbox=image_bbox,
                children=[image_block_id],
            ),
        ],
    )


class RasterOCRDetectorTests(unittest.TestCase):
    """验证局部翻译图片的 OCR 确认与阴性行为。"""

    def detect(self, target_ocr_text: str):
        """运行一组中译英大图片候选。"""

        source = make_page("source", "这是需要翻译的中文正文内容。", "source")
        target = make_page(
            "target",
            "This is the translated English page content.",
            "target",
        )
        match = RegionMatcher().match_page(source, target)
        provider = FakeOCRProvider(target_ocr_text)
        return RasterOCRDetector(provider).detect(
            source,
            target,
            match,
            lambda page, bbox: b"source-png",
            lambda page, bbox: b"target-png",
        )

    def test_detects_source_script_remaining_inside_changed_image(self) -> None:
        """译图仍保留足量中文时应生成 OCR 局部漏译问题。"""

        result = self.detect("功率模块 Supply chain 供应商")

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.processed_count, 1)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].type, IssueType.UNTRANSLATED_RASTER)
        self.assertEqual(result.issues[0].metrics["detection_mode"], "ocr_partial")

    def test_ignores_changed_image_when_target_ocr_is_translated(self) -> None:
        """译图 OCR 只含目标语言时不应报告图片漏译。"""

        result = self.detect("Power module supply chain structure")

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.processed_count, 1)
        self.assertEqual(result.issues, [])


if __name__ == "__main__":
    unittest.main()
