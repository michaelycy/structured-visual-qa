"""比较任务服务：归一化输入、串行执行流水线并管理渲染产物。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal

from document_qa.parsers import DocumentParsingError
from document_qa.pipeline import DocumentQAPipeline, RenderScope
from document_qa.profiles import RuleProfile
from document_qa.schemas import QAReport

from document_qa_server.services.normalization_service import (
    NormalizationError,
    NormalizationService,
)

# 一次只允许一个比较任务占用渲染目录，避免并发结果互相覆盖。
_run_lock = threading.Lock()


class CompareService:
    """封装一次比较任务的执行与产物归集。"""

    def __init__(
        self,
        *,
        artifacts_dir: Path,
        normalizer: NormalizationService | None = None,
    ) -> None:
        """注入产物根目录与可选归一化服务；渲染页写入 pages/ 子目录。"""

        self._artifacts_dir = artifacts_dir
        self._render_dir = artifacts_dir / "pages"
        self._normalizer = normalizer or NormalizationService(
            artifacts_dir=artifacts_dir
        )

    def run(
        self,
        source: Path,
        target: Path,
        *,
        profile: RuleProfile,
        render: bool = True,
        render_scope: RenderScope = "issues",
    ) -> tuple[QAReport, dict[str, list[str]]]:
        """执行比较并返回报告与渲染页文件名索引。

        非 PDF 输入先经 LibreOffice 归一化；报告 metadata 记录
        normalized_from，提示验收人结论含转换因素。
        可能抛出 DocumentParsingError / NormalizationError。
        """

        source_pdf, source_origin = self._ensure_pdf(source)
        target_pdf, target_origin = self._ensure_pdf(target)
        # 归一化发生时给偏移类阈值叠加转换噪声容差（Profile 副本上改，
        # 不污染用户配置；core 检测逻辑保持无来源感知）。
        effective_profile = profile
        if source_origin or target_origin:
            noise = profile.detectors.thresholds.conversion_noise_ratio
            thresholds = profile.detectors.thresholds.model_copy(
                update={
                    "shifted_ratio": min(
                        1.0, profile.detectors.thresholds.shifted_ratio + noise
                    ),
                    "severely_shifted_ratio": min(
                        1.0,
                        profile.detectors.thresholds.severely_shifted_ratio + noise,
                    ),
                }
            )
            effective_profile = profile.model_copy(
                update={
                    "detectors": profile.detectors.model_copy(
                        update={"thresholds": thresholds}
                    )
                }
            )
        with _run_lock:
            report = DocumentQAPipeline(profile=effective_profile).compare(
                source_pdf,
                target_pdf,
                render_dir=self._render_dir if render else None,
                render_scope=render_scope,
            )
        # 在流水线产物之上补记归一化来源，提示验收人结论含转换因素。
        origins = {"source": source_origin, "target": target_origin}
        if any(origins.values()):
            report = report.model_copy(
                update={"metadata": {**report.metadata, "normalized_from": origins}}
            )
        rendered = self._index_rendered() if render else {"source": [], "target": []}
        return report, rendered

    def _ensure_pdf(self, path: Path) -> tuple[Path, str | None]:
        """PDF 直接返回；Office 格式归一化为 PDF 并返回原格式标记。"""

        if path.suffix.lower() == ".pdf":
            return path, None
        normalized, origin = self._normalizer.normalize(path)
        return normalized, origin

    def render_root(self) -> Path:
        """返回渲染页根目录，供静态文件挂载使用。"""

        return self._render_dir

    def _index_rendered(self) -> dict[str, list[str]]:
        """列出两侧已渲染页面的文件名，供前端按需拼接图片 URL。"""

        index: dict[str, list[str]] = {}
        for side in ("source", "target"):
            side_dir = self._render_dir / side
            index[side] = (
                sorted(path.name for path in side_dir.glob("page-*.png"))
                if side_dir.is_dir()
                else []
            )
        return index
