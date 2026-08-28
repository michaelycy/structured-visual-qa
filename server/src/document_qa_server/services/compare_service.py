"""比较任务服务：归一化输入、执行流水线、管理渲染产物与任务状态。

异步模式下 compare 登记任务返回 task_id，由 BackgroundTasks 线程执行
（沿用同一把互斥锁，保持单 worker 语义）；同步模式行为与历史版本一致。
"""

from __future__ import annotations

import threading
import uuid
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from document_qa.parsers import DocumentParsingError
from document_qa.pipeline import DocumentQAPipeline, RenderScope
from document_qa.glossary import Glossary
from document_qa.profiles import RuleProfile
from document_qa.schemas import QAReport

from document_qa_server.observability import log_event
from document_qa_server.persistence import Database
from document_qa_server.services.normalization_service import (
    NormalizationError,
    NormalizationService,
)

# 一次只允许一个比较任务占用渲染目录，避免并发结果互相覆盖。
_run_lock = threading.Lock()

TaskStatus = Literal["queued", "running", "done", "error"]


def _sanitize_error(exc: Exception) -> str:
    """把异常转成可给前端的用户可读信息，抹去服务器本机路径。

    PyMuPDF/LibreOffice 的异常常内嵌完整文件路径（用户不需要也不应
    看到服务器目录结构）；产物根目录替换为占位符，其余文本保留。
    """

    import re

    text = str(exc)
    # 产物目录绝对路径 → 相对标记；任意类 Unix 绝对路径 → 只留文件名。
    root = "/Users/"
    if root in text:
        text = re.sub(r"/Users/[\w.-]+/\S*", "<服务器路径>", text)
    return text[:500]


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
    created_at: float = field(default_factory=time.monotonic)


class CompareService:
    """封装比较任务的执行、产物归集与异步任务注册表。"""

    def __init__(
        self,
        *,
        artifacts_dir: Path,
        normalizer: NormalizationService | None = None,
        database: Database | None = None,
    ) -> None:
        """注入产物根目录与可选归一化/持久化服务；渲染页写入 pages/ 子目录。"""

        self._artifacts_dir = artifacts_dir
        self._render_dir = artifacts_dir / "pages"
        self._normalizer = normalizer or NormalizationService(
            artifacts_dir=artifacts_dir
        )
        self._database = database
        self._tasks: dict[str, TaskState] = {}
        self._tasks_lock = threading.Lock()
        self._recover_interrupted_tasks()

    # 终态任务保留时长：结果已被前端取走或超时弃取后释放内存。
    _TERMINAL_TTL_SECONDS = 3600
    # 排队任务上限：比较是 CPU 密集重活，无限排队会拖垮线程池并
    # 让后提交任务的等待时间不可预期；超限直接拒绝并提示稍后再试。
    _MAX_QUEUED_TASKS = 3

    class QueueFullError(Exception):
        """排队任务数已达上限。"""

    def submit(self, source: Path, target: Path, *, displays: tuple[str, str]) -> str:
        """登记任务并返回 task_id（queued 状态）。

        queued 任务达到上限时抛 QueueFullError，由路由转 429。
        """

        self._evict_expired_tasks()
        with self._tasks_lock:
            queued = sum(
                1 for task in self._tasks.values() if task.status == "queued"
            )
            if queued >= self._MAX_QUEUED_TASKS:
                raise self.QueueFullError(
                    f"排队任务已达上限（{self._MAX_QUEUED_TASKS}），请等待进行中的任务完成后再提交"
                )
            task_id = uuid.uuid4().hex[:12]
            self._tasks[task_id] = TaskState(
                status="queued",
                source_path=str(source),
                target_path=str(target),
                source_display=displays[0],
                target_display=displays[1],
            )
        # 任务生命周期同步落库：服务重启后 /api/tasks 仍可查到历史任务，
        # 进行中的任务会被标记为重启中断而不是凭空消失。
        self._persist_task(task_id, "queued")
        log_event(
            "task_submitted",
            task_id=task_id,
            source=displays[0],
            target=displays[1],
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
        source_password: str | None = None,
        target_password: str | None = None,
        history_callback: (
            Callable[[dict, Path, Path, str, str, dict[str, list[str]]], str] | None
        ) = None,
    ) -> None:
        """在当前线程执行已登记的任务（供 BackgroundTasks 调用）。

        history_callback(report_dict, source, target, s_display, t_display, rendered)
        返回对比记录 ID，在比较成功后调用。密码只透传给流水线，
        不写入任务状态（TaskState）与历史记录。
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
                source_password=source_password,
                target_password=target_password,
            )
        except Exception as exc:
            # 兜底捕获一切异常（对抗审查 M-1：只捕解析/归一化两类时，
            # 磁盘满等运行时错误会让任务永久卡在 running，前端无限轮询）。
            message = _sanitize_error(exc)
            log_event("task_state", task_id=task_id, status="error", error=message)
            self._update(task_id, status="error", error=message)
            return
        report_dict = report.model_dump(mode="json")
        state = self._peek(task_id)
        record_id = None
        if history_callback and state:
            try:
                record_id = history_callback(
                    report_dict,
                    source,
                    target,
                    state.source_display or source.name,
                    state.target_display or target.name,
                    rendered,
                )
            except Exception as exc:
                # 报告与历史记录必须形成完整业务结果；持久化失败不能让任务
                # 永久停在 running，也不能把无历史锚点的结果伪装成成功。
                self._update(
                    task_id,
                    status="error",
                    error=f"报告持久化失败: {_sanitize_error(exc)}",
                )
                return
        self._update(
            task_id,
            status="done",
            report=report_dict,
            rendered=rendered,
            history_record_id=record_id,
        )

    def get_task(self, task_id: str) -> TaskState | None:
        """查询任务状态；内存未命中时回落数据库（重启后可查）。"""

        with self._tasks_lock:
            state = self._tasks.get(task_id)
        if state is not None:
            return state
        return self._load_task_from_db(task_id)

    def run(
        self,
        source: Path,
        target: Path,
        *,
        profile: RuleProfile,
        render: bool = True,
        render_scope: RenderScope = "issues",
        glossary: Glossary | None = None,
        source_password: str | None = None,
        target_password: str | None = None,
    ) -> tuple[QAReport, dict[str, list[str]]]:
        """同步执行比较并返回报告与渲染页文件名索引。

        非 PDF 输入先经 LibreOffice 归一化；报告 metadata 记录
        normalized_from。可能抛出 DocumentParsingError / NormalizationError。
        密码仅用于打开密码 PDF 的解析与渲染，不落入任何产物。
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
                source_password=source_password,
                target_password=target_password,
            )
            rendered = (
                self._index_rendered(render_dir) if render else {"source": [], "target": []}
            )
            # rendered 中的路径是相对 pages/ 根的完整段（含任务目录）。
        # 在流水线产物之上补记归一化来源，提示验收人结论含转换因素。
        origins = {"source": source_origin, "target": target_origin}
        metadata = dict(report.metadata)
        if any(origins.values()):
            metadata["normalized_from"] = origins
        if glossary is not None:
            # 报告保存本次实际术语版本引用，持久化层据此建立不可变外键。
            metadata["glossary_reference"] = glossary.reference
        if metadata != report.metadata:
            report = report.model_copy(
                update={"metadata": metadata}
            )
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
        """合并更新任务状态字段，并把生命周期变化同步落库。"""

        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            for key, value in fields.items():
                setattr(task, key, value)
        # 状态迁移与关键锚点（错误信息、历史记录 ID）落库；
        # 内存中的报告大对象不入库（由 history/comparison_reports 承载）。
        if "status" in fields or "error" in fields or "history_record_id" in fields:
            self._persist_task(
                task_id,
                fields.get("status") or task.status,
                error=fields.get("error", task.error),
                history_record_id=fields.get(
                    "history_record_id", task.history_record_id
                ),
            )
            # 状态转换打点：事后排障的任务时间线来源。
            log_event(
                "task_state",
                task_id=task_id,
                status=fields.get("status") or task.status,
                error=(fields.get("error") or "")[:200] or None,
                history_record_id=fields.get("history_record_id"),
            )

    # ---- 任务生命周期持久化 -------------------------------------------------

    def _persist_task(
        self,
        task_id: str,
        status: str,
        *,
        error: str | None = None,
        history_record_id: str | None = None,
    ) -> None:
        """把任务状态 UPSERT 到 async_tasks；数据库不可用时静默降级为纯内存。"""

        if self._database is None:
            return
        state = self._peek(task_id)
        now = Database.now()
        try:
            with self._database.transaction() as connection:
                connection.execute(
                    "INSERT INTO async_tasks("
                    "task_id, status, source_display, target_display, "
                    "history_record_id, error, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(task_id) DO UPDATE SET "
                    "status = excluded.status, "
                    "history_record_id = excluded.history_record_id, "
                    "error = excluded.error, "
                    "updated_at = excluded.updated_at",
                    (
                        task_id,
                        status,
                        (state.source_display if state else ""),
                        (state.target_display if state else ""),
                        history_record_id,
                        error,
                        now,
                        now,
                    ),
                )
        except Exception:
            # 持久化失败不应阻断比较主流程；此时任务退化为重启不可恢复。
            return

    def _load_task_from_db(self, task_id: str) -> TaskState | None:
        """重启后按 task_id 读回终态任务（不含报告大对象）。"""

        if self._database is None:
            return None
        try:
            with self._database.connect() as connection:
                row = connection.execute(
                    "SELECT task_id, status, source_display, target_display, "
                    "history_record_id, error FROM async_tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
        except Exception:
            return None
        if row is None:
            return None
        log_event(
            "task_recovered",
            task_id=task_id,
            status=row["status"],
        )
        return TaskState(
            status=row["status"],
            source_path="",
            target_path="",
            source_display=row["source_display"],
            target_display=row["target_display"],
            report=None,
            rendered=None,
            error=row["error"],
            history_record_id=row["history_record_id"],
            created_at=0.0,
        )

    def _recover_interrupted_tasks(self) -> None:
        """服务启动时把上次运行遗留的 queued/running 任务标记为中断。

        后台线程随进程消亡，这些任务不可能再推进；明确标记错误比
        让前端轮询 404 更诚实（报告若已落历史仍可从对比记录回查）。
        """

        if self._database is None:
            return
        try:
            with self._database.transaction() as connection:
                cursor = connection.execute(
                    "UPDATE async_tasks SET status = 'error', "
                    "error = '服务重启，任务中断；已完成的结果请从对比记录查看', "
                    "updated_at = ? "
                    "WHERE status IN ('queued', 'running')",
                    (Database.now(),),
                )
            if cursor.rowcount:
                log_event("task_interrupted", count=cursor.rowcount)
        except Exception:
            return

    def _peek(self, task_id: str) -> TaskState | None:
        """持锁读取任务快照。"""

        with self._tasks_lock:
            return self._tasks.get(task_id)

    def _evict_expired_tasks(self) -> None:
        """清理超时的终态任务（对抗审查 L-1：注册表无界增长）。

        运行中/排队任务永不清理；done/error 超过 TTL 后移除，
        结果已持久化在 history，前端仍可从对比记录回查。
        """

        cutoff = time.monotonic() - self._TERMINAL_TTL_SECONDS
        with self._tasks_lock:
            expired = [
                task_id
                for task_id, task in self._tasks.items()
                if task.status in ("done", "error")
                and task.created_at < cutoff
            ]
            for task_id in expired:
                del self._tasks[task_id]

    @staticmethod
    def _index_rendered(task_dir: Path) -> dict[str, list[str]]:
        """列出该任务两侧已渲染页面的文件名，供前端拼接图片 URL。

        任务目录隔离后索引天然是本次比较的快照，无跨任务串染。
        """

        prefix = task_dir.name
        index: dict[str, list[str]] = {}
        for side in ("source", "target"):
            side_dir = task_dir / side
            index[side] = (
                sorted(
                    f"{prefix}/{side}/{path.name}"
                    for path in side_dir.glob("page-*.png")
                )
                if side_dir.is_dir()
                else []
            )
        return index
