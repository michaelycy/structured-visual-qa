"""术语库服务：基于 SQLite 的版本化术语库生命周期管理。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from document_qa.glossary import Glossary, default_glossary
from document_qa_server.persistence import Database


@dataclass(frozen=True)
class GlossarySummary:
    """列表项：标识、名称、版本与条目数。"""

    filename: str
    glossary_id: str
    name: str
    version: int
    entry_count: int
    reference: str


class GlossaryService:
    """封装术语库的校验、版本保存、读取与归档。"""

    def __init__(self, *, artifacts_dir: Path, database: Database | None = None) -> None:
        """注入 SQLite；首次启动幂等导入旧 glossaries/*.json。"""

        self._database = database or Database(artifacts_dir=artifacts_dir)
        self._legacy_dir = artifacts_dir / "glossaries"
        self._save_validated(default_glossary())
        self._import_legacy()

    @staticmethod
    def default() -> Glossary:
        """返回内置示例术语库，作为界面初始值。"""

        return default_glossary()

    def save(self, data: dict) -> tuple[str, str]:
        """校验并保存术语库版本，返回数据库定位符与版本引用。"""

        validated = Glossary.model_validate(data)
        filename = self._save_validated(validated)
        return f"sqlite:{filename}", validated.reference

    def list(self) -> list[GlossarySummary]:
        """列出未归档的自定义术语库摘要。"""

        default_filename = self._filename(default_glossary())
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT filename, glossary_id, name, version, entry_count "
                "FROM glossary_versions "
                "WHERE status = 'active' AND filename <> ? ORDER BY filename",
                (default_filename,),
            ).fetchall()
        return [
            GlossarySummary(
                filename=row["filename"],
                glossary_id=row["glossary_id"],
                name=row["name"],
                version=row["version"],
                entry_count=row["entry_count"],
                reference=f"{row['glossary_id']}@{row['version']}",
            )
            for row in rows
        ]

    def get(self, filename: str) -> Glossary:
        """按兼容文件名读取术语库，包括已归档历史版本。"""

        self._validate_filename(filename)
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM glossary_versions WHERE filename = ?",
                (filename,),
            ).fetchone()
        if row is None:
            raise ValueError(f"术语库不存在: {filename}")
        return Glossary.model_validate_json(row["payload_json"])

    def load_by_reference(self, reference: str) -> Glossary:
        """按版本引用（id@version）加载术语库。"""

        if "@" not in reference:
            raise ValueError(f"无效术语库引用: {reference}")
        glossary_id, raw_version = reference.rsplit("@", 1)
        try:
            version = int(raw_version)
        except ValueError as exc:
            raise ValueError(f"无效术语库引用: {reference}") from exc
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM glossary_versions "
                "WHERE glossary_id = ? AND version = ?",
                (glossary_id, version),
            ).fetchone()
        if row is None:
            raise ValueError(f"术语库不存在: {reference}")
        return Glossary.model_validate_json(row["payload_json"])

    def delete(self, filename: str) -> None:
        """归档自定义术语库；历史引用仍可继续加载。"""

        self._validate_filename(filename)
        if filename == self._filename(default_glossary()):
            raise ValueError("内置默认术语库不可归档")
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE glossary_versions SET status = 'archived', updated_at = ? "
                "WHERE filename = ? AND status = 'active'",
                (Database.now(), filename),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"术语库不存在: {filename}")

    def _save_validated(self, glossary: Glossary) -> str:
        """保存完整术语 JSON 及摘要，家族+版本冲突时幂等更新。"""

        filename = self._filename(glossary)
        payload = glossary.model_dump_json()
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = Database.now()
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO glossary_versions("
                "glossary_id, version, filename, name, status, description, entry_count, "
                "payload_json, payload_sha256, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(glossary_id, version) DO UPDATE SET "
                "filename=excluded.filename, name=excluded.name, description=excluded.description, "
                "entry_count=excluded.entry_count, payload_json=excluded.payload_json, "
                "payload_sha256=excluded.payload_sha256, updated_at=excluded.updated_at",
                (
                    glossary.glossary_id,
                    glossary.version,
                    filename,
                    glossary.name,
                    glossary.description,
                    len(glossary.entries),
                    payload,
                    digest,
                    now,
                    now,
                ),
            )
        return filename

    def _import_legacy(self) -> None:
        """幂等导入旧术语 JSON，非法文件保留并跳过。"""

        import_key = "glossaries_json_v1"
        if self._database.legacy_import_done(import_key):
            return
        paths = sorted(self._legacy_dir.glob("*.json")) if self._legacy_dir.is_dir() else []
        imported = 0
        for path in paths:
            try:
                self._save_validated(
                    Glossary.model_validate_json(path.read_text(encoding="utf-8"))
                )
                imported += 1
            except Exception:
                continue
        self._database.mark_legacy_import(
            import_key, source_count=len(paths), imported_count=imported
        )

    @staticmethod
    def _filename(glossary: Glossary) -> str:
        """生成兼容旧 API 的术语库版本文件名。"""

        return f"{glossary.glossary_id}-v{glossary.version}.json"

    @staticmethod
    def _validate_filename(filename: str) -> None:
        """拒绝路径分隔和上级路径。"""

        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("无效术语库文件名")
