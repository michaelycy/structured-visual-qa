"""比较任务服务：归一化输入、执行流水线、管理渲染产物与任务状态。

异步模式下 compare 登记任务返回 task_id，由 BackgroundTasks 线程执行
（沿用同一把互斥锁，保持单 worker 语义）；同步模式行为与历史版本一致。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from document_qa.parsers import DocumentParsingError
from document_qa.pipeline import DocumentQAPipeline, RenderScope
from document_qa.glossary import Glossary
from document_qa.profiles import RuleProfile
from document_qa.schemas import QAReport

from document_qa_server.services.normalization_service import (
    NormalizationError,
    NormalizationService,
)

# 一次只允许一个比较任务占用渲染目录，避免并发结果互相覆盖。
_run_lock = threading.Lock()

TaskStatus = Literal["queued", "running", "done", "error"]


@dataclass
class TaskState:
    """一个比较任务的运行状态与结果引用。"""

    status: TaskStatus
    source_path: str = ""
    target_path: str = ""
    source_display: str = ""
    target_display: str = ""
    report: dict | None = None
    rendered: dict[str, list[str]] | None = None
    error: str | None = None
    history_record_id: str | None = field(default=None)


class CompareService:
    """封装比较任务的执行、产物归集与异步任务注册表。"""

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
        self._tasks: dict[str, TaskState] = {}
        self._tasks_lock = threading.Lock()

    def submit(self, source: Path, target: Path, *, displays: tuple[str, str]) -> str:
        """登记任务并返回 task_id（queued 状态）。"""

        task_id = uuid.uuid4().hex[:12]
        with self._tasks_lock:
            self._tasks[task_id] = TaskState(
                status="queued",
                source_path=str(source),
                target_path=str(target),
                source_display=displays[0],
                target_display=displays[1],
            )
        return task_id

    def execute(
        self,
        task_id: str,
        source: Path,
        target: Path,
        *,
        profile: RuleProfile,
        render: bool = True,
        render_scope: RenderScope = "issues",
        glossary: Glossary | None = None,
        history_callback: Callable[[dict, Path, Path, str, str], str] | None = None,
    ) -> None:
        """在当前线程执行已登记的任务（供 BackgroundTasks 调用）。

        history_callback(report_dict, source, target, s_display, t_display)
        返回对比记录 ID，在比较成功后调用。
        """

        self._update(task_id, status="running")
        try:
            report, rendered = self.run(
                source,
                target,
                profile=profile,
                render=render,
                render_scope=render_scope,
                glossary=glossary,
            )
        except Exception as exc:
            # 兜底捕获一切异常（对抗审查 M-1：只捕解析/归一化两类时，
            # 磁盘满等运行时错误会让任务永久卡在 running，前端无限轮询）。
            self._update(task_id, status="error", error=str(exc))
            return
        report_dict = report.model_dump(mode="json")
        state = self._peek(task_id)
        record_id = None
        if history_callback and state:
            record_id = history_callback(
                report_dict,
                source,
                target,
                state.source_display or source.name,
                state.target_display or target.name,
            )
        self._update(
            task_id,
            status="done",
            report=report_dict,
            rendered=rendered,
            history_record_id=record_id,
        )

    def get_task(self, task_id: str) -> TaskState | None:
        """查询任务状态；不存在返回 None。"""

        with self._tasks_lock:
            return self._tasks.get(task_id)

    def run(
        self,
        source: Path,
        target: Path,
        *,
        profile: RuleProfile,
        render: bool = True,
        render_scope: RenderScope = "issues",
        glossary: Glossary | None = None,
    ) -> tuple[QAReport, dict[str, list[str]]]:
        """同步执行比较并返回报告与渲染页文件名索引。

        非 PDF 输入先经 LibreOffice 归一化；报告 metadata 记录
        normalized_from。可能抛出 DocumentParsingError / NormalizationError。
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
        # 渲染产物按任务隔离（对抗审查 M-2）：共享 pages/ 会串染——
        # 上一个任务的残留页混入本次索引，且并发任务的写入互相覆盖。
        # 每任务独立子目录 + 索引在锁内生成，读的是本次任务的快照。
        render_dir = None
        with _run_lock:
            if render:
                render_dir = self._render_dir / f"task-{uuid.uuid4().hex[:10]}"
            report = DocumentQAPipeline(
                profile=effective_profile, glossary=glossary
            ).compare(
                source_pdf,
                target_pdf,
                render_dir=render_dir,
                render_scope=render_scope,
            )
            rendered = (
                self._index_rendered(render_dir) if render else {"source": [], "target": []}
            )
        # 在流水线产物之上补记归一化来源，提示验收人结论含转换因素。
        origins = {"source": source_origin, "target": target_origin}
        if any(origins.values()):
            report = report.model_copy(
                update={"metadata": {**report.metadata, "normalized_from": origins}}
            )
        rendered = self._index_rendered() if render else {"source": [], "target": []}
        return report, rendered

    def render_root(self) -> Path:
        """返回渲染页根目录，供静态文件挂载使用。"""

        return self._render_dir

    def _ensure_pdf(self, path: Path) -> tuple[Path, str | None]:
        """PDF 直接返回；Office 格式归一化为 PDF 并返回原格式标记。"""

        if path.suffix.lower() == ".pdf":
            return path, None
        normalized, origin = self._normalizer.normalize(path)
        return normalized, origin

    def _update(self, task_id: str, **fields) -> None:
        """合并更新任务状态字段。"""

        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            for key, value in fields.items():
                setattr(task, key, value)

    def _peek(self, task_id: str) -> TaskState | None:
        """持锁读取任务快照。"""

        with self._tasks_lock:
            return self._tasks.get(task_id)

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
