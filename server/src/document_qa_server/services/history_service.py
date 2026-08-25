"""对比记录服务：SQLite 摘要索引与完整 QAReport 原子持久化。"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from document_qa.profiles import RuleProfile, default_rule_profile
from document_qa.schemas import QAReport
from document_qa_server.observability import log_event
from document_qa_server.persistence import Database


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
    rendered: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    source_path: str | None = None
    target_path: str | None = None


class CompareHistoryService:
    """封装对比记录追加、列表、读取、旧 JSON 导入与数量淘汰。"""

    def __init__(
        self,
        *,
        artifacts_dir: Path,
        max_records: int = 100,
        database: Database | None = None,
    ) -> None:
        """注入 SQLite；首次启动幂等导入旧 history/*.json。

        启动即清扫孤儿渲染目录：渲染失败的中间产物没有任何记录
        引用，是 pages/ 无界增长的主要来源。
        """

        self._artifacts_dir = artifacts_dir
        self._database = database or Database(artifacts_dir=artifacts_dir)
        self._legacy_dir = artifacts_dir / "history"
        self._max_records = max_records
        self._import_legacy()
        self._collect_orphan_render_dirs()

    def add(
        self,
        *,
        report: dict[str, Any],
        source_path: str,
        target_path: str,
        source_display: str,
        target_display: str,
        rendered: dict[str, Any] | None = None,
    ) -> CompareRecord:
        """在一个事务中保存摘要和完整报告，并返回完整记录。"""

        now = Database.now()
        compact = now.replace("-", "").replace(":", "").replace("T", "-")
        record_id = f"{compact[0:15]}-{compact[16:19]}-{uuid.uuid4().hex[:4]}"
        record = self._save(
            record_id=record_id,
            created_at=now,
            report=report,
            source_path=source_path,
            target_path=target_path,
            source_display=source_display,
            target_display=target_display,
            rendered=rendered,
        )
        self._evict_expired()
        return record

    def list(self) -> list[CompareRecord]:
        """按时间倒序返回轻量摘要，不读取完整报告正文。"""

        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT r.*, sf.storage_path AS source_path, tf.storage_path AS target_path "
                "FROM comparison_records r "
                "JOIN stored_files sf ON sf.file_id = r.source_file_id "
                "JOIN stored_files tf ON tf.file_id = r.target_file_id "
                "ORDER BY r.created_at DESC, r.record_id DESC"
            ).fetchall()
        return [self._record_from_row(row, report=None, include_paths=False) for row in rows]

    def get(self, record_id: str) -> CompareRecord:
        """按 ID 读取摘要和完整报告；报告 JSON 重新通过 QAReport 校验。"""

        self._validate_id(record_id)
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT r.*, rp.report_json, sf.storage_path AS source_path, "
                "tf.storage_path AS target_path "
                "FROM comparison_records r "
                "JOIN comparison_reports rp ON rp.record_id = r.record_id "
                "JOIN stored_files sf ON sf.file_id = r.source_file_id "
                "JOIN stored_files tf ON tf.file_id = r.target_file_id "
                "WHERE r.record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"记录不存在或已淘汰: {record_id}")
        # 旧报告的 Profile 快照不会包含后来新增的 detector toggle、阈值或
        # Issue 扣分上限。读取边界先递归补默认键，再交给当前严格 Schema
        # 校验；数据库中的历史 JSON 和当时的分数、状态均保持不变。
        legacy_report = json.loads(row["report_json"])
        compatible_report = self._upgrade_legacy_report(legacy_report)
        report = QAReport.model_validate(compatible_report).model_dump(mode="json")
        return self._record_from_row(row, report=report, include_paths=True)

    def _save(
        self,
        *,
        record_id: str,
        created_at: str,
        report: dict[str, Any],
        source_path: str,
        target_path: str,
        source_display: str,
        target_display: str,
        rendered: dict[str, Any] | None,
    ) -> CompareRecord:
        """执行一次可指定 ID 的原子写，供在线新增与遗留导入共用。"""

        compatible_report = self._upgrade_legacy_report(report)
        validated = QAReport.model_validate(compatible_report)
        report_dict = validated.model_dump(mode="json")
        report_json = json.dumps(
            report_dict, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        report_bytes = report_json.encode("utf-8")
        profile = self._profile_from_report(report_dict)
        issue_total = sum(report_dict.get("summary", {}).get("issue_counts", {}).values())
        normalized = (report_dict.get("metadata") or {}).get("normalized_from")
        with self._database.transaction() as connection:
            source_id = self._register_file(
                connection, Path(source_path), source_display, origin="legacy"
            )
            target_id = self._register_file(
                connection, Path(target_path), target_display, origin="legacy"
            )
            self._ensure_profile(connection, profile)
            # 通过两侧内容身份自动关联样本；工作台无需信任客户端传 sample_id。
            sample_row = connection.execute(
                "SELECT sample_id FROM samples WHERE source_file_id = ? "
                "AND target_file_id = ? AND status = 'active' "
                "ORDER BY updated_at DESC LIMIT 1",
                (source_id, target_id),
            ).fetchone()
            sample_id = sample_row["sample_id"] if sample_row else None
            connection.execute(
                "INSERT OR IGNORE INTO comparison_records("
                "record_id, source_file_id, target_file_id, sample_id, source_display, "
                "target_display, status, document_score, page_count, issue_total, "
                "rule_profile_id, rule_profile_version, rule_profile_reference, "
                "normalized_from_json, rendered_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    source_id,
                    target_id,
                    sample_id,
                    source_display,
                    target_display,
                    report_dict["status"],
                    report_dict["document_score"],
                    report_dict["summary"]["pages"],
                    issue_total,
                    profile.profile_id,
                    profile.version,
                    report_dict["rule_profile_reference"],
                    self._json_or_none(normalized),
                    self._json_or_none(rendered),
                    created_at,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO comparison_reports("
                "record_id, schema_version, report_json, byte_size, report_sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    1,
                    report_json,
                    len(report_bytes),
                    hashlib.sha256(report_bytes).hexdigest(),
                    created_at,
                ),
            )
            glossary_reference = (report_dict.get("metadata") or {}).get(
                "glossary_reference"
            )
            if glossary_reference:
                glossary_id, separator, raw_version = glossary_reference.rpartition("@")
                if not separator or not raw_version.isdigit():
                    raise ValueError(f"报告包含无效术语库引用: {glossary_reference}")
                glossary_version = int(raw_version)
                exists = connection.execute(
                    "SELECT 1 FROM glossary_versions "
                    "WHERE glossary_id = ? AND version = ?",
                    (glossary_id, glossary_version),
                ).fetchone()
                if exists is None:
                    raise ValueError(f"报告引用的术语库版本不存在: {glossary_reference}")
                connection.execute(
                    "INSERT OR IGNORE INTO comparison_glossaries("
                    "record_id, glossary_id, glossary_version, glossary_reference) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        record_id,
                        glossary_id,
                        glossary_version,
                        glossary_reference,
                    ),
                )
        return CompareRecord(
            record_id=record_id,
            created_at=created_at,
            source_display=source_display,
            target_display=target_display,
            status=report_dict["status"],
            document_score=report_dict["document_score"],
            pages=report_dict["summary"]["pages"],
            issue_total=issue_total,
            rule_profile_reference=report_dict["rule_profile_reference"],
            normalized_from=normalized,
            rendered=rendered,
            report=report_dict,
            source_path=source_path,
            target_path=target_path,
        )

    def _import_legacy(self) -> None:
        """幂等导入旧完整历史 JSON；原文件不修改、不删除。"""

        import_key = "history_json_v1"
        if self._database.legacy_import_done(import_key):
            return
        paths = (
            [
                path
                for path in sorted(self._legacy_dir.glob("*.json"))
                if not path.name.endswith(".summary.json")
            ]
            if self._legacy_dir.is_dir()
            else []
        )
        imported = 0
        for path in paths:
            try:
                legacy = CompareRecord.model_validate_json(path.read_text(encoding="utf-8"))
                if legacy.report is None or not legacy.source_path or not legacy.target_path:
                    continue
                self._save(
                    record_id=legacy.record_id,
                    created_at=legacy.created_at,
                    report=legacy.report,
                    source_path=legacy.source_path,
                    target_path=legacy.target_path,
                    source_display=legacy.source_display,
                    target_display=legacy.target_display,
                    rendered=legacy.rendered,
                )
                imported += 1
            except Exception:
                continue
        self._database.mark_legacy_import(
            import_key, source_count=len(paths), imported_count=imported
        )
        self._evict_expired()

    def _evict_expired(self) -> None:
        """超过上限时删除最旧数据库记录；完整报告通过外键级联删除。

        被淘汰记录独占引用的渲染任务目录（pages/task-*）一并回收——
        渲染 PNG 动辄数百 MB，是产物目录膨胀的主因（P1 GC）。
        """

        evicted_rendered: list[str] = []
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT record_id, rendered_json FROM comparison_records "
                "ORDER BY created_at DESC, record_id DESC LIMIT -1 OFFSET ?",
                (self._max_records,),
            ).fetchall()
            if not rows:
                return
            # 淘汰前收集这些记录引用的任务目录，供删除后回收判定。
            for row in rows:
                evicted_rendered.append(row["rendered_json"] or "")
            connection.executemany(
                "DELETE FROM comparison_records WHERE record_id = ?",
                [(row["record_id"],) for row in rows],
            )
        self._collect_orphan_render_dirs()

    def _collect_orphan_render_dirs(self) -> None:
        """删除不再被任何对比记录引用的渲染任务目录。

        rendered_json 中的路径形如 task-{id}/source/page-0001.png，
        任务目录前缀即引用锚点；同一目录可能被多条记录引用（缓存
        命中场景），必须全量查存活引用后才能删除。
        """

        pages_dir = self._artifacts_dir / "pages"
        if not pages_dir.is_dir():
            return
        # 存活记录引用的任务目录前缀集合。
        referenced: set[str] = set()
        with self._database.connect() as connection:
            for row in connection.execute(
                "SELECT rendered_json FROM comparison_records "
                "WHERE rendered_json IS NOT NULL"
            ):
                for name in self._task_dir_names(row["rendered_json"] or ""):
                    referenced.add(name)
        removed = 0
        for task_dir in pages_dir.glob("task-*"):
            if task_dir.name not in referenced:
                shutil.rmtree(task_dir, ignore_errors=True)
                removed += 1
        if removed:
            log_event("render_garbage", removed_dirs=removed, kept=len(referenced))

    @staticmethod
    def _task_dir_names(rendered_json: str) -> set[str]:
        """从 rendered_json 提取任务目录名（task- 前缀，去重）。"""

        try:
            rendered = json.loads(rendered_json) if rendered_json else {}
        except json.JSONDecodeError:
            return set()
        if not isinstance(rendered, dict):
            return set()
        names: set[str] = set()
        for paths in rendered.values():
            if not isinstance(paths, list):
                continue
            for entry in paths:
                if isinstance(entry, str) and "/" in entry:
                    head = entry.split("/", 1)[0]
                    if head.startswith("task-"):
                        names.add(head)
        return names

    @staticmethod
    def _register_file(connection, path: Path, display: str, *, origin: str) -> str:
        """登记现存或遗留缺失文件；内容摘要相同的文件自然复用。"""

        resolved = path.expanduser().resolve()
        if resolved.is_file():
            digest = hashlib.sha256()
            with resolved.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            sha256 = digest.hexdigest()
            file_id = sha256
            size = resolved.stat().st_size
            availability = "present"
        else:
            sha256 = None
            file_id = "legacy-" + hashlib.sha256(str(resolved).encode()).hexdigest()
            size = None
            availability = "missing"
        existing = connection.execute(
            "SELECT file_id FROM stored_files WHERE file_id = ? OR storage_path = ?",
            (file_id, str(resolved)),
        ).fetchone()
        if existing:
            return existing["file_id"]
        connection.execute(
            "INSERT INTO stored_files(file_id, sha256, original_name, storage_path, "
            "file_format, size_bytes, origin, availability, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                sha256,
                display or resolved.name,
                str(resolved),
                resolved.suffix.lower(),
                size,
                origin,
                availability,
                Database.now(),
            ),
        )
        return file_id

    @staticmethod
    def _ensure_profile(connection, profile: RuleProfile) -> None:
        """确保报告引用的规则版本存在，满足对比记录复合外键。"""

        payload = profile.model_dump_json()
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = Database.now()
        connection.execute(
            "INSERT OR IGNORE INTO rule_profile_versions("
            "profile_id, version, filename, name, status, description, payload_json, "
            "payload_sha256, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                profile.profile_id,
                profile.version,
                f"{profile.profile_id}-v{profile.version}.json",
                profile.name,
                profile.status.value,
                profile.description,
                payload,
                digest,
                now,
                now,
            ),
        )

    @staticmethod
    def _profile_from_report(report: dict[str, Any]) -> RuleProfile:
        """从报告快照恢复规则版本；旧报告缺快照时回退内置默认值。"""

        snapshot = report.get("rule_profile_snapshot")
        return RuleProfile.model_validate(snapshot) if snapshot else default_rule_profile()

    @staticmethod
    def _upgrade_legacy_report(report: dict[str, Any]) -> dict[str, Any]:
        """补齐旧报告后来新增的 Profile 字段，旧值优先且不重算结论。

        QAReport 内嵌完整规则快照。新增 Issue 类型后，旧快照可能缺少对应
        toggle 或扣分上限而无法通过当前 Schema；迁移只递归补默认键。
        """

        upgraded = json.loads(json.dumps(report))
        snapshot = upgraded.get("rule_profile_snapshot")
        if not snapshot:
            return upgraded

        def merge(defaults: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
            result = dict(defaults)
            for key, value in legacy.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merge(result[key], value)
                else:
                    result[key] = value
            return result

        upgraded["rule_profile_snapshot"] = merge(
            default_rule_profile().model_dump(mode="json"), snapshot
        )
        return upgraded

    @staticmethod
    def _record_from_row(row, *, report, include_paths: bool) -> CompareRecord:
        """把 SQLite 行转换为稳定的 API 模型。"""

        return CompareRecord(
            record_id=row["record_id"],
            created_at=row["created_at"],
            source_display=row["source_display"],
            target_display=row["target_display"],
            status=row["status"],
            document_score=row["document_score"],
            pages=row["page_count"],
            issue_total=row["issue_total"],
            rule_profile_reference=row["rule_profile_reference"],
            normalized_from=json.loads(row["normalized_from_json"])
            if row["normalized_from_json"]
            else None,
            rendered=json.loads(row["rendered_json"]) if row["rendered_json"] else None,
            report=report,
            source_path=row["source_path"] if include_paths else None,
            target_path=row["target_path"] if include_paths else None,
        )

    @staticmethod
    def _json_or_none(value: Any) -> str | None:
        """把可选结构编码为稳定 JSON。"""

        return (
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            if value is not None
            else None
        )

    @staticmethod
    def _validate_id(record_id: str) -> None:
        """限制历史 ID 字符，避免异常输入进入查询与日志。"""

        if not all(ch.isalnum() or ch in "-_" for ch in record_id):
            raise ValueError("无效记录 ID")
