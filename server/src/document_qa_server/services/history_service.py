"""对比记录服务：比较任务历史的持久化与查询。

每次 compare 落一条记录（摘要 + 完整报告 + 输入路径），供界面的
「对比记录」页列出并重新加载查看。存储沿用 JSON 文件策略：记录
目录按时间倒序扫描，单文件自包含，无需数据库。

跨进程互斥：Web 服务与 MCP 服务可能同时写同一 history/ 目录
（对抗审查 M-7），线程锁无法跨进程，add/淘汰经目录级文件锁串行。
"""

from __future__ import annotations

import contextlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field

from document_qa_server.services.filelock import file_lock


class CompareRecord(BaseModel):
    """一次比较任务的历史记录。"""

    record_id: str = Field(min_length=1)
    created_at: str
    source_display: str
    target_display: str
    status: str
    document_score: float
    pages: int
    issue_total: int
    rule_profile_reference: str
    normalized_from: dict[str, Any] | None = None
    # 完整报告与输入路径，重新查看时使用；列表查询时不加载。
    report: dict[str, Any] | None = None
    source_path: str | None = None
    target_path: str | None = None


class CompareHistoryService:
    """封装对比记录的追加、列表与读取。"""

    def __init__(self, *, artifacts_dir: Path, max_records: int = 100) -> None:
        """注入产物根目录；记录写入 history/ 子目录，超量淘汰最旧。"""

        self._history_dir = artifacts_dir / "history"
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._max_records = max_records
        # 目录级文件锁：Web 与 MCP 双进程同目录写时串行化。
        self._lockfile_path = self._history_dir / ".lock"

    @contextlib.contextmanager
    def _file_lock(self) -> Iterator[None]:
        """跨进程排它锁（fcntl + 线程锁）；Windows 回退为仅线程锁。"""

        with file_lock(self._lockfile_path):
            yield

    def add(
        self,
        *,
        report: dict[str, Any],
        source_path: str,
        target_path: str,
        source_display: str,
        target_display: str,
    ) -> CompareRecord:
        """保存一条对比记录并返回；文件名含时间戳保证唯一。

        record_id 在持锁后生成：锁外生成时并发任务同毫秒启动会
        碰撞并静默互相覆盖（对抗测试 F1 实锤：20 并发写只剩 1 条）。
        文件锁同时串行化跨进程写入与淘汰（对抗审查 M-7）。
        """

        now = datetime.now(timezone.utc)
        with self._file_lock():
            record_id = (
                now.strftime("%Y%m%d-%H%M%S")
                + f"-{now.microsecond // 1000:03d}"
                + f"-{uuid.uuid4().hex[:4]}"
            )
            record = CompareRecord(
                record_id=record_id,
                created_at=now.isoformat(),
                source_display=source_display,
                target_display=target_display,
                status=report.get("status", ""),
                document_score=report.get("document_score", 0.0),
                pages=report.get("summary", {}).get("pages", 0),
                issue_total=sum(
                    report.get("summary", {}).get("issue_counts", {}).values()
                ),
                rule_profile_reference=report.get("rule_profile_reference", ""),
                normalized_from=(report.get("metadata") or {}).get("normalized_from"),
                report=report,
                source_path=source_path,
                target_path=target_path,
            )
            path = self._history_dir / f"{record_id}.json"
            # 原子写：临时文件替换，避免中断留半份记录。
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(path)
            # 列表页只读的轻量摘要 sidecar：剥离 report 与本地路径大字段，
            # 避免 list() 每次全量解析大报告。
            summary = record.model_copy(
                update={"report": None, "source_path": None, "target_path": None}
            )
            summary_path = path.with_suffix(".summary.json")
            summary_temporary = summary_path.with_suffix(".summary.json.tmp")
            summary_temporary.write_text(
                summary.model_dump_json(indent=2), encoding="utf-8"
            )
            summary_temporary.replace(summary_path)
            self._evict_expired()
        return record

    def list(self) -> list[CompareRecord]:
        """按时间倒序列出全部记录（优先读轻量 sidecar，不含完整报告）。"""

        records: list[CompareRecord] = []
        seen: set[str] = set()
        for path in sorted(self._history_dir.glob("*.summary.json")):
            try:
                record = CompareRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                continue  # 损坏 sidecar 跳过，不影响列表
            records.append(record)
            seen.add(record.record_id)
        # 兼容升级前无 sidecar 的旧记录：读全量文件并剥离大字段。
        for path in sorted(self._history_dir.glob("*.json")):
            if path.name.endswith(".summary.json") or path.stem in seen:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue  # 损坏记录跳过，不影响列表
            data.pop("report", None)  # 列表视图剥离大字段
            try:
                records.append(CompareRecord.model_validate(data))
            except Exception:
                continue
        records.sort(key=lambda item: item.record_id, reverse=True)
        return records

    def get(self, record_id: str) -> CompareRecord:
        """按 ID 读取完整记录（含报告）；不存在或刚被淘汰时抛 ValueError。"""

        if not all(ch.isalnum() or ch in "-_" for ch in record_id):
            raise ValueError("无效记录 ID")
        path = self._history_dir / f"{record_id}.json"
        try:
            return CompareRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            # is_file 检查与读取之间可能被另一进程的淘汰删除（M-7）。
            raise ValueError(f"记录不存在或已淘汰: {record_id}") from exc

    def _evict_expired(self) -> None:
        """超过上限时删除最旧记录及其 sidecar（调用方需持锁）。"""

        records = sorted(
            (
                path
                for path in self._history_dir.glob("*.json")
                if not path.name.endswith(".summary.json")
            ),
            key=lambda path: path.name,
        )
        excess = len(records) - self._max_records
        for path in records[: max(0, excess)]:
            path.unlink(missing_ok=True)
            path.with_suffix(".summary.json").unlink(missing_ok=True)
