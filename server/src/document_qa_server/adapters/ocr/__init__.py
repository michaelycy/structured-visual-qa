"""可选 OCR 适配器工厂。"""

from pathlib import Path

from document_qa.ocr import OCRProvider

from document_qa_server.adapters.ocr.paddle import PaddleOCRProvider
from document_qa_server.settings import ServerSettings


def build_ocr_provider(
    settings: ServerSettings, *, artifacts_dir: Path | None = None
) -> OCRProvider | None:
    """根据服务配置构建 OCR 适配器；关闭时不导入任何推理框架。"""

    if not settings.ocr_enabled:
        return None
    if settings.ocr_provider != "paddle":
        raise ValueError(f"不支持的 OCR Provider: {settings.ocr_provider}")
    return PaddleOCRProvider(
        device=settings.ocr_device,
        language=settings.ocr_language,
        ocr_version=settings.ocr_version,
        cache_dir=settings.ocr_cache_dir
        or (artifacts_dir or settings.artifacts_dir) / "ocr-cache",
        detection_model_dir=settings.ocr_detection_model_dir,
        recognition_model_dir=settings.ocr_recognition_model_dir,
        cpu_threads=settings.ocr_cpu_threads,
        detection_model_name=settings.ocr_detection_model_name,
        recognition_model_name=settings.ocr_recognition_model_name,
    )


__all__ = ["PaddleOCRProvider", "build_ocr_provider"]
