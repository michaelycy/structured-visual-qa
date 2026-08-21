"""复核闭环服务：基于 SQLite 保存 Issue 人工判定。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from document_qa_server.persistence import Database

ReviewDecision = Literal["confirmed", "false_positive", "ignored"]


class IssueReview(BaseModel):
    """一条 Issue 的人工判定记录。"""

    issue_id: str = Field(min_length=1)
    decision: ReviewDecision
    note: str = ""
    reviewed_at: str


class TaskReviewRecord(BaseModel):
    """一次比较任务的复核身份与全部 Issue 判定。"""

    source_document_id: str
    target_document_id: str
    rule_profile_reference: str
    decisions: dict[str, IssueReview] = Field(default_factory=dict)
    updated_at: str = ""


class ReviewService:
    """封装复核判定的事务写入、查询与旧 JSON 导入。"""

    def __init__(self, *, artifacts_dir: Path, database: Database | None = None) -> None:
        """注入 SQLite；首次启动幂等导入旧 reviews/*.json。"""

        self._database = database or Database(artifacts_dir=artifacts_dir)
        self._legacy_dir = artifacts_dir / "reviews"
        self._import_legacy()

    def save_decision(
        self,
        task_id: str,
        report_summary: dict,
        issue_id: str,
        decision: ReviewDecision,
        note: str = "",
    ) -> TaskReviewRecord:
        """在一个事务中保存复核任务身份和单条 Issue 最新结论。"""

        self._validate_id(task_id)
        if not issue_id:
            raise ValueError("Issue ID 不能为空")
        now = Database.now()
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO review_tasks(task_id, source_document_id, target_document_id, "
                "rule_profile_reference, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET updated_at=excluded.updated_at",
                (
                    task_id,
                    report_summary.get("source_document_id", ""),
                    report_summary.get("target_document_id", ""),
                    report_summary.get("rule_profile_reference", ""),
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO review_decisions(task_id, issue_id, decision, note, reviewed_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(task_id, issue_id) DO UPDATE SET "
                "decision=excluded.decision, note=excluded.note, reviewed_at=excluded.reviewed_at",
                (task_id, issue_id, decision, note, now),
            )
        return self.load(task_id)

    def load(
        self, task_id: str, report_summary: dict | None = None
    ) -> TaskReviewRecord:
        """加载复核任务；不存在且提供摘要时返回尚未落库的空记录。"""

        self._validate_id(task_id)
        with self._database.connect() as connection:
            task = connection.execute(
                "SELECT * FROM review_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            rows = connection.execute(
                "SELECT * FROM review_decisions WHERE task_id = ? ORDER BY issue_id",
                (task_id,),
            ).fetchall()
        if task is None:
            if report_summary is None:
                raise ValueError("复核任务不存在")
            return TaskReviewRecord(
                source_document_id=report_summary.get("source_document_id", ""),
                target_document_id=report_summary.get("target_document_id", ""),
                rule_profile_reference=report_summary.get("rule_profile_reference", ""),
            )
        decisions = {
            row["issue_id"]: IssueReview(
                issue_id=row["issue_id"],
                decision=row["decision"],
                note=row["note"],
                reviewed_at=row["reviewed_at"],
            )
            for row in rows
        }
        return TaskReviewRecord(
            source_document_id=task["source_document_id"],
            target_document_id=task["target_document_id"],
            rule_profile_reference=task["rule_profile_reference"],
            decisions=decisions,
            updated_at=task["updated_at"],
        )

    def _import_legacy(self) -> None:
        """幂等导入旧复核 JSON；原文件继续保留。"""

        import_key = "reviews_json_v1"
        if self._database.legacy_import_done(import_key):
            return
        paths = sorted(self._legacy_dir.glob("*.json")) if self._legacy_dir.is_dir() else []
        imported = 0
        for path in paths:
            try:
                task_id = path.stem
                record = TaskReviewRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                summary = {
                    "source_document_id": record.source_document_id,
                    "target_document_id": record.target_document_id,
                    "rule_profile_reference": record.rule_profile_reference,
                }
                if not record.decisions:
                    continue
                with self._database.transaction() as connection:
                    connection.execute(
                        "INSERT OR IGNORE INTO review_tasks("
                        "task_id, source_document_id, target_document_id, "
                        "rule_profile_reference, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (
                            task_id,
                            summary["source_document_id"],
                            summary["target_document_id"],
                            summary["rule_profile_reference"],
                            record.updated_at or Database.now(),
                        ),
                    )
                    connection.executemany(
                        "INSERT OR IGNORE INTO review_decisions("
                        "task_id, issue_id, decision, note, reviewed_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        [
                            (
                                task_id,
                                review.issue_id,
                                review.decision,
                                review.note,
                                review.reviewed_at,
                            )
                            for review in record.decisions.values()
                        ],
                    )
                imported += 1
            except Exception:
                continue
        self._database.mark_legacy_import(
            import_key, source_count=len(paths), imported_count=imported
        )

    @staticmethod
    def _validate_id(task_id: str) -> None:
        """任务 ID 只允许安全字符。"""

        if not task_id or not all(ch.isalnum() or ch in "-_" for ch in task_id):
            raise ValueError("无效任务 ID")
