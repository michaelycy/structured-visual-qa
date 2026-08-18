"""对比记录服务：比较任务历史的持久化与查询。

每次 compare 落一条记录（摘要 + 完整报告 + 输入路径），供界面的
「对比记录」页列出并重新加载查看。存储沿用 JSON 文件策略：记录
目录按时间倒序扫描，单文件自包含，无需数据库。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


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
        self._lock = threading.Lock()

    def add(
        self,
        *,
        report: dict[str, Any],
        source_path: str,
        target_path: str,
        source_display: str,
        target_display: str,
    ) -> CompareRecord:
        """保存一条对比记录并返回；文件名含时间戳保证唯一。"""

        now = datetime.now(timezone.utc)
        record_id = now.strftime("%Y%m%d-%H%M%S") + f"-{now.microsecond // 1000:03d}"
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
        with self._lock:
            path = self._history_dir / f"{record_id}.json"
            # 原子写：临时文件替换，避免中断留半份记录。
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(path)
            self._evict_expired()
        return record

    def list(self) -> list[CompareRecord]:
        """按时间倒序列出全部记录（不含完整报告，轻量摘要）。"""

        records: list[CompareRecord] = []
        for path in self._history_dir.glob("*.json"):
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
        """按 ID 读取完整记录（含报告）；不存在时抛 ValueError。"""

        if not all(ch.isalnum() or ch in "-_" for ch in record_id):
            raise ValueError("无效记录 ID")
        path = self._history_dir / f"{record_id}.json"
        if not path.is_file():
            raise ValueError(f"记录不存在: {record_id}")
        return CompareRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def _evict_expired(self) -> None:
        """超过上限时删除最旧记录（调用方需持锁）。"""

        records = sorted(self._history_dir.glob("*.json"), key=lambda p: p.name)
        excess = len(records) - self._max_records
        for path in records[: max(0, excess)]:
            path.unlink(missing_ok=True)
