"""PaddleOCR 本地推理适配器。"""

from __future__ import annotations

import json
import os
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np

from document_qa.ocr import OCRLine, OCRResult
from document_qa.schemas import BoundingBox


class PaddleOCRProvider:
    """把 PaddleOCR 3.x 输出转换成 core 的稳定 OCRResult。"""

    def __init__(
        self,
        *,
        device: str = "cpu",
        language: str = "ch",
        ocr_version: str = "PP-OCRv6",
        cache_dir: Path | None = None,
        detection_model_dir: Path | None = None,
        recognition_model_dir: Path | None = None,
        cpu_threads: int = 0,
        detection_model_name: str | None = None,
        recognition_model_name: str | None = None,
    ) -> None:
        """保存运行配置；模型在第一次候选识别时只初始化一次。

        cpu_threads > 0 时把推理线程数传给 PaddleOCR（默认单核，
        T40 评估确认这是图像密集文档 OCR 慢的主因之一）；
        detection/recognition_model_name 允许经配置直接切换 mobile
        档模型（如 PP-OCRv5_mobile_det/rec），PaddleOCR 自动下载。
        """

        self.device = device
        self.language = language
        self.ocr_version = ocr_version
        self.cache_dir = cache_dir
        self.detection_model_dir = detection_model_dir
        self.recognition_model_dir = recognition_model_dir
        self.cpu_threads = cpu_threads
        self.detection_model_name = detection_model_name
        self.recognition_model_name = recognition_model_name
        self._pipeline: Any | None = None
        self._lock = threading.Lock()

    @property
    def provider_name(self) -> str:
        """返回报告中使用的适配器名称。"""

        return "paddleocr"

    @property
    def model_fingerprint(self) -> str:
        """返回包版本、模型版本、语言和设备的组合标识。"""

        try:
            package_version = version("paddleocr")
        except PackageNotFoundError:
            package_version = "not-installed"
        return (
            f"paddleocr-{package_version}:{self.ocr_version}:"
            f"{self.language}:{self.device}"
        )

    def recognize(self, image_png: bytes) -> OCRResult:
        """识别内存 PNG，不落盘且不保留输入图片。"""

        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("PaddleOCR 图像解码依赖未安装") from exc

        encoded = np.frombuffer(image_png, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("无法解码 OCR 候选 PNG")
        outputs = list(self._get_pipeline().predict(image))
        lines: list[OCRLine] = []
        for output in outputs:
            lines.extend(self._parse_output(output))
        return OCRResult(
            image_width=int(image.shape[1]),
            image_height=int(image.shape[0]),
            lines=lines,
        )

    def _get_pipeline(self):
        """线程安全地延迟初始化 PaddleOCR 模型。"""

        if self._pipeline is not None:
            return self._pipeline
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            try:
                if self.cache_dir is not None:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    os.environ.setdefault(
                        "PADDLE_PDX_CACHE_HOME", str(self.cache_dir.resolve())
                    )
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise RuntimeError(
                    "OCR 已启用，但未安装 server 的 ocr-paddle 可选依赖"
                ) from exc
            options: dict[str, Any] = {
                "device": self.device,
                "lang": self.language,
                "ocr_version": self.ocr_version,
                # PDF 候选裁剪已经方向正常且无透视形变，关闭额外三个模型。
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            }
            if self.detection_model_dir is not None:
                options["text_detection_model_dir"] = str(
                    self.detection_model_dir
                )
            if self.recognition_model_dir is not None:
                options["text_recognition_model_dir"] = str(
                    self.recognition_model_dir
                )
            if self.cpu_threads > 0:
                options["cpu_threads"] = self.cpu_threads
            if self.detection_model_name:
                options["text_detection_model_name"] = self.detection_model_name
            if self.recognition_model_name:
                options["text_recognition_model_name"] = self.recognition_model_name
            self._pipeline = PaddleOCR(**options)
            return self._pipeline

    @classmethod
    def _parse_output(cls, output: Any) -> list[OCRLine]:
        """兼容 PaddleOCR 3.x Result 对象的 JSON/字典表现形式。"""

        payload = getattr(output, "json", output)
        if callable(payload):
            payload = payload()
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise TypeError("无法解析 PaddleOCR 输出")
        values = payload.get("res", payload)
        texts = cls._as_list(values.get("rec_texts", []))
        scores = cls._as_list(values.get("rec_scores", []))
        box_values = values.get("rec_boxes")
        if box_values is None:
            box_values = values.get("rec_polys")
        if box_values is None:
            box_values = values.get("dt_polys")
        boxes = cls._as_list(box_values)
        lines = []
        for text, score, box in zip(texts, scores, boxes):
            bbox = cls._bbox_from_value(box)
            if bbox is None:
                continue
            lines.append(
                OCRLine(text=str(text), confidence=float(score), bbox=bbox)
            )
        return lines

    @staticmethod
    def _as_list(value: Any) -> list:
        """把 ndarray、元组或列表统一成普通列表。"""

        if hasattr(value, "tolist"):
            value = value.tolist()
        return list(value) if value is not None else []

    @classmethod
    def _bbox_from_value(cls, value: Any) -> BoundingBox | None:
        """把四值矩形或四点多边形转换为最小外接框。"""

        raw = cls._as_list(value)
        if len(raw) == 4 and all(isinstance(item, (int, float)) for item in raw):
            x0, y0, x1, y1 = (float(item) for item in raw)
        else:
            points = [cls._as_list(point) for point in raw]
            points = [point for point in points if len(point) >= 2]
            if not points:
                return None
            x0 = min(float(point[0]) for point in points)
            y0 = min(float(point[1]) for point in points)
            x1 = max(float(point[0]) for point in points)
            y1 = max(float(point[1]) for point in points)
        if x1 <= x0 or y1 <= y0:
            return None
        return BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
