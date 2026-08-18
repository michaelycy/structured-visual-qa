"""比较任务服务：串行执行流水线并管理渲染产物。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal

from document_qa.parsers import DocumentParsingError
from document_qa.pipeline import DocumentQAPipeline, RenderScope
from document_qa.profiles import RuleProfile
from document_qa.schemas import QAReport

# 一次只允许一个比较任务占用渲染目录，避免并发结果互相覆盖。
_run_lock = threading.Lock()


class CompareService:
    """封装一次比较任务的执行与产物归集。"""

    def __init__(self, *, artifacts_dir: Path) -> None:
        """注入产物根目录；渲染页写入其 pages/ 子目录。"""

        self._artifacts_dir = artifacts_dir
        self._render_dir = artifacts_dir / "pages"

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

        可能抛出 DocumentParsingError，由调用方（API 层）转换为协议错误。
        """

        with _run_lock:
            report = DocumentQAPipeline(profile=profile).compare(
                source,
                target,
                render_dir=self._render_dir if render else None,
                render_scope=render_scope,
            )
        rendered = self._index_rendered() if render else {"source": [], "target": []}
        return report, rendered

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
