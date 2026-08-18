"""复核闭环服务：Issue 人工判定的持久化与汇总。

验收场景需要人工对每条 Issue 签核（确认/误报/忽略），判定结果
持久化为 JSON 文件，也是规则校准（阈值回溯）的数据来源。
存储刻意简单：每次比较任务一个 JSON 文件，不引入数据库。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ReviewDecision = Literal["confirmed", "false_positive", "ignored"]


class IssueReview(BaseModel):
    """一条 Issue 的人工判定记录。"""

    issue_id: str = Field(min_length=1)
    decision: ReviewDecision
    note: str = ""
    reviewed_at: str


class TaskReviewRecord(BaseModel):
    """一次比较任务的复核记录：报告摘要 + 全部判定。"""

    source_document_id: str
    target_document_id: str
    rule_profile_reference: str
    decisions: dict[str, IssueReview] = Field(default_factory=dict)
    updated_at: str = ""


class ReviewService:
    """封装复核记录的读写与统计。"""

    def __init__(self, *, artifacts_dir: Path) -> None:
        """注入产物根目录；复核记录写入其 reviews/ 子目录。"""

        self._reviews_dir = artifacts_dir / "reviews"
        self._reviews_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def _task_lock(self, task_id: str) -> threading.Lock:
        """每个任务一把锁，避免并发写同一文件。"""

        with self._registry_lock:
            if task_id not in self._locks:
                self._locks[task_id] = threading.Lock()
            return self._locks[task_id]

    def _task_path(self, task_id: str) -> Path:
        """任务 ID 只允许安全字符，防止路径穿越。"""

        if not all(ch.isalnum() or ch in "-_" for ch in task_id):
            raise ValueError("无效任务 ID")
        return self._reviews_dir / f"{task_id}.json"

    def save_decision(
        self,
        task_id: str,
        report_summary: dict,
        issue_id: str,
        decision: ReviewDecision,
        note: str = "",
    ) -> TaskReviewRecord:
        """记录一条判定并原子保存整个任务记录。"""

        with self._task_lock(task_id):
            record = self.load(task_id, report_summary)
            record.decisions[issue_id] = IssueReview(
                issue_id=issue_id,
                decision=decision,
                note=note,
                reviewed_at=datetime.now(timezone.utc).isoformat(),
            )
            record.updated_at = datetime.now(timezone.utc).isoformat()
            path = self._task_path(task_id)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(path)
            return record

    def load(
        self, task_id: str, report_summary: dict | None = None
    ) -> TaskReviewRecord:
        """加载任务记录；不存在时用报告摘要初始化空记录。"""

        path = self._task_path(task_id)
        if path.is_file():
            return TaskReviewRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        if report_summary is None:
            raise ValueError("复核任务不存在")
        return TaskReviewRecord(
            source_document_id=report_summary.get("source_document_id", ""),
            target_document_id=report_summary.get("target_document_id", ""),
            rule_profile_reference=report_summary.get(
                "rule_profile_reference", ""
            ),
        )
