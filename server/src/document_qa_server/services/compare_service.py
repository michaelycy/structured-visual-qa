"""比较任务服务：任务状态管理 + 子进程隔离执行（T23）。

异步模式下 compare 登记任务返回 task_id；任务在 spawn 子进程中执行
完整流水线（含可选 PaddleOCR），API 进程只等待结果——OCR 推理占满
CPU 时接口仍能即时响应，子进程崩溃也不会拖垮服务。同步模式
（DQA_ASYNC_MODE=false / MCP）保留在当前进程执行的历史行为。两条
路径共用 compare_worker.execute_compare，避免执行逻辑漂移。
"""

from __future__ import annotations

import json
import multiprocessing
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from document_qa.parsers import DocumentParsingError
from document_qa.pipeline import RenderScope
from document_qa.glossary import Glossary
from document_qa.ocr import OCRProvider
from document_qa.profiles import RuleProfile
from document_qa.schemas import QAReport

from document_qa_server.observability import log_event
from document_qa_server.persistence import Database
from document_qa_server.services.compare_worker import execute_compare, run_compare

# 一次只允许一个比较任务（子进程）执行并占用渲染目录，避免并发互相覆盖。
_run_lock = threading.Lock()

TaskStatus = Literal["queued", "running", "done", "error"]


class CompareParsingError(Exception):
    """比较输入无法被核心解析，供协议层映射为校验失败。"""


def _sanitize_error(exc: object) -> str:
    """把异常或子进程错误文本转成用户可读信息，抹去服务器本机路径。

    PyMuPDF/LibreOffice 的异常常内嵌完整文件路径（用户不需要也不应
    看到服务器目录结构）；产物根目录替换为占位符，其余文本保留。
    接受任意对象：子进程错误以纯字符串经管道回传，走同一净化入口。
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
        database: Database | None = None,
        ocr_provider: OCRProvider | None = None,
        worker_threads: int = 0,
    ) -> None:
        """注入产物根目录与可选持久化/OCR 依赖；渲染页写入 pages/ 子目录。

        worker_threads 是比较子进程的 BLAS/推理线程数上限（0 不限制）；
        ocr_provider 仅供同步路径使用，异步子进程按 DQA_ 环境变量重建。
        """

        self._artifacts_dir = artifacts_dir
        self._render_dir = artifacts_dir / "pages"
        self._database = database
        self._ocr_provider = ocr_provider
        self._worker_threads = worker_threads
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
        """在隔离子进程中执行已登记的任务（供 BackgroundTasks 调用）。

        流水线（含可选 PaddleOCR）运行在 spawn 子进程里，API 进程只在
        管道上等待结果：OCR 推理吃满 CPU 时其他接口仍能即时响应，子进程
        崩溃也不会拖垮服务。history_callback(report_dict, source, target,
        s_display, t_display, rendered) 返回对比记录 ID，在比较成功后调用。
        密码经 spawn 管道内存传递，不写入任务状态（TaskState）与历史记录。
        """

        self._update(task_id, status="running")
        payload = {
            "artifacts_dir": str(self._artifacts_dir),
            "source": str(source),
            "target": str(target),
            "profile_json": profile.model_dump_json(),
            "glossary_json": glossary.model_dump_json() if glossary else None,
            "render": render,
            "render_scope": render_scope,
            "source_password": source_password,
            "target_password": target_password,
            "worker_threads": self._worker_threads,
            # 子进程把流水线阶段进度追加写入该 JSONL，/api/tasks 轮询
            # 读末行展示"当前阶段 + 页级简报"；文件按任务隔离。
            "progress_path": str(self._task_progress_path(task_id)),
        }
        error_message: str | None = None
        result: dict = {}
        try:
            # 单 worker 语义：同一时刻最多一个比较子进程，沿用既有互斥锁。
            with _run_lock:
                result = self._execute_in_subprocess(payload)
            if "error" in result:
                error_message = _sanitize_error(result["error"])
        except Exception as exc:
            # 兜底捕获一切异常（对抗审查 M-1：磁盘满等运行时错误不能让
            # 任务永久卡在 running，前端无限轮询）。
            error_message = _sanitize_error(exc)
        if error_message is not None:
            log_event(
                "task_state", task_id=task_id, status="error", error=error_message
            )
            self._update(task_id, status="error", error=error_message)
            return
        report_dict = result["report"]
        rendered = result["rendered"]
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

    def list_tasks(self, limit: int = 20) -> list[dict]:
        """列出最近的比较任务（含进行中），供质检记录页展示任务动态。

        数据以 async_tasks 表为准（每次状态迁移同步落库，重启中断任务
        会被标记 error，不会展示陈旧的 running）。进行中任务附带流水线
        进度简报；数据库不可用时返回空列表而不是报错——动态展示属于
        增强信息，不能影响记录页主列表。
        """

        if self._database is None:
            return []
        try:
            with self._database.connect() as connection:
                rows = connection.execute(
                    "SELECT task_id, status, source_display, target_display, "
                    "history_record_id, error, created_at, updated_at "
                    "FROM async_tasks ORDER BY created_at DESC LIMIT ?",
                    (max(1, min(limit, 100)),),
                ).fetchall()
        except Exception:
            return []
        tasks: list[dict] = []
        for row in rows:
            task = {
                "task_id": row["task_id"],
                "status": row["status"],
                "source_display": row["source_display"],
                "target_display": row["target_display"],
                "history_record_id": row["history_record_id"],
                "error": row["error"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "progress": None,
            }
            if task["status"] in ("queued", "running"):
                task["progress"] = self.task_progress(task["task_id"])
            tasks.append(task)
        return tasks

    def task_progress(self, task_id: str) -> dict | None:
        """读取任务的最新流水线进度（进度 JSONL 末行）；无进度时为 None。"""

        path = self._task_progress_path(task_id)
        try:
            if not path.is_file():
                return None
            with path.open("r", encoding="utf-8") as handle:
                last_line = ""
                for line in handle:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
            return json.loads(last_line) if last_line else None
        except Exception:
            # 进度文件损坏/被清理时退化为"无简报"，不影响任务状态展示。
            return None

    def _task_progress_path(self, task_id: str) -> Path:
        """任务进度 JSONL 的固定路径；task_id 来自服务端生成的 uuid。"""

        return self._artifacts_dir / "tasks" / task_id / "progress.jsonl"

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
        """同步执行比较并返回报告与渲染页文件名索引（当前进程内）。

        供 DQA_ASYNC_MODE=false 回归路径与 MCP 使用，行为与历史版本
        一致；异步任务的进程隔离执行见 execute()。非 PDF 输入先经
        LibreOffice 归一化，可能抛出 CompareParsingError /
        NormalizationError。密码仅用于打开密码 PDF 的解析与渲染，
        不落入任何产物。
        """

        try:
            # 单 worker 语义：同步路径与异步子进程共用同一把互斥锁。
            with _run_lock:
                return execute_compare(
                    artifacts_dir=self._artifacts_dir,
                    source=source,
                    target=target,
                    profile=profile,
                    glossary=glossary,
                    ocr_provider=self._ocr_provider,
                    render=render,
                    render_scope=render_scope,
                    source_password=source_password,
                    target_password=target_password,
                )
        except DocumentParsingError as exc:
            raise CompareParsingError(str(exc)) from exc

    def _execute_in_subprocess(self, payload: dict) -> dict:
        """spawn 子进程运行 run_compare，并回收结果或错误。

        daemon=True：主进程退出（含 --reload 重启）时子进程一并终止，
        不留孤儿任务继续占用 CPU；中断任务由启动恢复逻辑标记 error。
        管道写端在父进程侧立即关闭，子进程退出后 recv 不会挂起。
        """

        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=run_compare, args=(payload, sender), daemon=True
        )
        process.start()
        sender.close()
        try:
            result: dict = receiver.recv()
        except EOFError:
            # 子进程未发送任何结果即退出：通常是推理框架段错误或被 OOM 杀死。
            result = {"error": "比较子进程异常退出（未返回结果），请重试"}
        finally:
            receiver.close()
        process.join()
        return result

    def render_root(self) -> Path:
        """返回渲染页根目录，供静态文件挂载使用。"""

        return self._render_dir

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
