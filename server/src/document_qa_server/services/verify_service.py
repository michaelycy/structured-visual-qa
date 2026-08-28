"""分阶段验证服务：驱动 StagedVerifier 并持久化各阶段产物。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from document_qa.verify import Stage, StagedVerifier, save_artifacts


@dataclass(frozen=True)
class VerifyStageResult:
    """一个验证阶段的传输结构：摘要、数据与产物路径。"""

    stage: str
    summary: str
    data: dict
    artifact: str


class VerifyService:
    """封装分阶段验证的执行与产物落盘。"""

    def __init__(self, *, artifacts_dir: Path) -> None:
        """注入产物根目录；阶段 JSON 写入其 stages/ 子目录。"""

        self._artifacts_dir = artifacts_dir

    def run(
        self, source: Path, target: Path, *, stop_after: str
    ) -> list[VerifyStageResult]:
        """执行到指定阶段并返回逐阶段结果。"""

        artifacts = StagedVerifier().run(source, target, stop_after=Stage(stop_after))
        paths = save_artifacts(artifacts, self._artifacts_dir / "stages")
        return [
            VerifyStageResult(
                stage=artifact.stage.value,
                summary=artifact.summary,
                data=artifact.data,
                artifact=str(path),
            )
            for artifact, path in zip(artifacts, paths, strict=True)
        ]
