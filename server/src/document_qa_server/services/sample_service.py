"""样本管理服务：持久化源/目标文档对并提供工作台载入能力。"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from document_qa_server.persistence import Database
from document_qa_server.services.file_service import ACCEPTED_SUFFIXES


@dataclass(frozen=True)
class SampleRecord:
    """样本列表与详情使用的稳定数据模型。"""

    sample_id: str
    name: str
    description: str
    origin: str
    status: str
    source_name: str
    source_path: str
    source_format: str
    target_name: str
    target_path: str
    target_format: str
    source_language: str
    target_language: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class BuiltinSampleScanResult:
    """一次内置样本目录扫描的结构化摘要。"""

    discovered: int
    created: int
    existing: int
    conflicts: tuple[str, ...]


class SampleService:
    """封装样本创建、查询、编辑、归档及内置样本发现。"""

    def __init__(
        self,
        *,
        artifacts_dir: Path,
        samples_dir: Path,
        database: Database | None = None,
    ) -> None:
        """注入 SQLite 和只读内置样例目录，并幂等建立可识别样本对。"""

        self._database = database or Database(artifacts_dir=artifacts_dir)
        self._samples_dir = samples_dir
        self._scan_lock = Lock()
        self.rescan_builtins()

    def create(
        self,
        *,
        name: str,
        description: str,
        source_path: Path,
        source_name: str,
        target_path: Path,
        target_name: str,
        source_language: str = "und",
        target_language: str = "und",
    ) -> SampleRecord:
        """把两个已安全上传的文件登记为用户样本对。"""

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("样本名称不能为空")
        sample_id = uuid.uuid4().hex[:16]
        now = Database.now()
        source_language = self._normalize_language(source_language)
        target_language = self._normalize_language(target_language)
        try:
            with self._database.transaction() as connection:
                source_id = self._register_file(
                    connection, source_path, source_name, origin="sample"
                )
                target_id = self._register_file(
                    connection, target_path, target_name, origin="sample"
                )
                connection.execute(
                    "INSERT INTO samples(sample_id, name, description, source_file_id, "
                    "target_file_id, origin, status, created_at, updated_at, "
                    "source_language, target_language) "
                    "VALUES (?, ?, ?, ?, ?, 'user', 'active', ?, ?, ?, ?)",
                    (
                        sample_id,
                        normalized_name,
                        description.strip(),
                        source_id,
                        target_id,
                        now,
                        now,
                        source_language,
                        target_language,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("样本名称已存在，或源文档与目标文档不能相同") from exc
        return self.get(sample_id)

    def list(self, *, include_archived: bool = False) -> list[SampleRecord]:
        """按更新时间倒序列出样本，默认隐藏已归档记录。"""

        where = "" if include_archived else "WHERE s.status = 'active'"
        with self._database.connect() as connection:
            rows = connection.execute(
                self._select_sql() + f" {where} ORDER BY s.updated_at DESC, s.name"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, sample_id: str) -> SampleRecord:
        """读取一个样本详情；不存在时抛出 ValueError。"""

        self._validate_id(sample_id)
        with self._database.connect() as connection:
            row = connection.execute(
                self._select_sql() + " WHERE s.sample_id = ?", (sample_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"样本不存在: {sample_id}")
        return self._from_row(row)

    def update(
        self,
        sample_id: str,
        *,
        name: str,
        description: str,
        source_language: str,
        target_language: str,
    ) -> SampleRecord:
        """修改用户样本名称、描述和语言对；内置样本保持只读。"""

        current = self.get(sample_id)
        if current.origin == "builtin":
            raise ValueError("内置样本不可修改")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("样本名称不能为空")
        source_language = self._normalize_language(source_language)
        target_language = self._normalize_language(target_language)
        try:
            with self._database.transaction() as connection:
                connection.execute(
                    "UPDATE samples SET name = ?, description = ?, source_language = ?, "
                    "target_language = ?, updated_at = ? "
                    "WHERE sample_id = ? AND status = 'active'",
                    (
                        normalized_name,
                        description.strip(),
                        source_language,
                        target_language,
                        Database.now(),
                        sample_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("样本名称已存在") from exc
        return self.get(sample_id)

    def archive(self, sample_id: str) -> None:
        """归档用户样本；文件和历史记录均不删除。"""

        current = self.get(sample_id)
        if current.origin == "builtin":
            raise ValueError("内置样本不可归档")
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE samples SET status = 'archived', updated_at = ? WHERE sample_id = ?",
                (Database.now(), sample_id),
            )

    def use(self, sample_id: str) -> SampleRecord:
        """返回可载入工作台的活动样本，并校验两侧文件仍然存在。"""

        record = self.get(sample_id)
        if record.status != "active":
            raise ValueError("样本已归档")
        if not Path(record.source_path).is_file() or not Path(record.target_path).is_file():
            raise ValueError("样本文档已丢失，无法载入")
        return record

    def rescan_builtins(self) -> BuiltinSampleScanResult:
        """重新扫描只读目录，只登记新增样本并返回冲突摘要。"""

        with self._scan_lock:
            pairs = self._discover_builtin_pairs()
            created = 0
            existing = 0
            conflicts: list[str] = []
            for source, target in pairs:
                pair_label = f"{source.name} → {target.name}"
                sample_id = "builtin-" + hashlib.sha256(
                    f"{source.resolve()}\0{target.resolve()}".encode()
                ).hexdigest()[:16]
                source_language, target_language = (
                    ("en", "zh-CN")
                    if "-en." in source.name and "-zh." in target.name
                    else ("und", "und")
                )
                try:
                    with self._database.transaction() as connection:
                        if connection.execute(
                            "SELECT 1 FROM samples WHERE sample_id = ?", (sample_id,)
                        ).fetchone():
                            existing += 1
                            continue
                        if connection.execute(
                            "SELECT 1 FROM samples WHERE name = ? COLLATE NOCASE",
                            (source.stem,),
                        ).fetchone():
                            conflicts.append(f"{pair_label}：样本名称已存在")
                            continue
                        source_id = self._register_file(
                            connection, source, source.name, origin="builtin"
                        )
                        target_id = self._register_file(
                            connection, target, target.name, origin="builtin"
                        )
                        if source_id == target_id:
                            raise ValueError("源文档与目标文档内容相同")
                        now = Database.now()
                        connection.execute(
                            "INSERT INTO samples(sample_id, name, description, "
                            "source_file_id, target_file_id, origin, status, created_at, "
                            "updated_at, source_language, target_language) "
                            "VALUES (?, ?, ?, ?, ?, 'builtin', 'active', ?, ?, ?, ?)",
                            (
                                sample_id,
                                source.stem,
                                "仓库内置只读样本对",
                                source_id,
                                target_id,
                                now,
                                now,
                                source_language,
                                target_language,
                            ),
                        )
                    created += 1
                except (OSError, sqlite3.IntegrityError, ValueError) as exc:
                    conflicts.append(f"{pair_label}：{exc}")
            return BuiltinSampleScanResult(
                discovered=len(pairs),
                created=created,
                existing=existing,
                conflicts=tuple(conflicts),
            )

    def _discover_builtin_pairs(self) -> list[tuple[Path, Path]]:
        """按 translated_ 与 en/zh 约定发现并去重内置样本对。"""

        if not self._samples_dir.is_dir():
            return []
        try:
            files = {
                path.name: path
                for path in self._samples_dir.iterdir()
                if path.is_file() and path.suffix.lower() in ACCEPTED_SUFFIXES
            }
        except OSError as exc:
            raise RuntimeError("无法读取内置样本目录") from exc
        pairs: dict[tuple[str, str], tuple[Path, Path]] = {}
        for name, target in files.items():
            if name.startswith("translated_") and name.removeprefix("translated_") in files:
                source = files[name.removeprefix("translated_")]
                pairs[(str(source.resolve()), str(target.resolve()))] = (source, target)
            if "-zh." in name:
                source_name = name.replace("-zh.", "-en.")
                if source_name in files:
                    source = files[source_name]
                    pairs[(str(source.resolve()), str(target.resolve()))] = (source, target)
        return [pairs[key] for key in sorted(pairs)]

    @staticmethod
    def _register_file(connection, path: Path, name: str, *, origin: str) -> str:
        """按内容摘要登记文件；同一物理内容跨样本复用一条元数据。"""

        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise ValueError(f"文件不存在: {resolved}")
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        file_id = digest.hexdigest()
        row = connection.execute(
            "SELECT file_id FROM stored_files WHERE file_id = ?", (file_id,)
        ).fetchone()
        if row:
            return row["file_id"]
        connection.execute(
            "INSERT INTO stored_files(file_id, sha256, original_name, storage_path, "
            "file_format, size_bytes, origin, availability, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'present', ?)",
            (
                file_id,
                file_id,
                name,
                str(resolved),
                resolved.suffix.lower(),
                resolved.stat().st_size,
                origin,
                Database.now(),
            ),
        )
        return file_id

    @staticmethod
    def _select_sql() -> str:
        """返回样本详情的公共关联查询。"""

        return (
            "SELECT s.*, sf.original_name AS source_name, sf.storage_path AS source_path, "
            "sf.file_format AS source_format, tf.original_name AS target_name, "
            "tf.storage_path AS target_path, tf.file_format AS target_format "
            "FROM samples s JOIN stored_files sf ON sf.file_id = s.source_file_id "
            "JOIN stored_files tf ON tf.file_id = s.target_file_id"
        )

    @staticmethod
    def _from_row(row) -> SampleRecord:
        """把 SQLite 行转换为服务稳定模型。"""

        return SampleRecord(
            sample_id=row["sample_id"],
            name=row["name"],
            description=row["description"],
            origin=row["origin"],
            status=row["status"],
            source_name=row["source_name"],
            source_path=row["source_path"],
            source_format=row["source_format"],
            target_name=row["target_name"],
            target_path=row["target_path"],
            target_format=row["target_format"],
            source_language=row["source_language"],
            target_language=row["target_language"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _validate_id(sample_id: str) -> None:
        """限制样本 ID 字符范围。"""

        if not sample_id or not all(ch.isalnum() or ch in "-_" for ch in sample_id):
            raise ValueError("无效样本 ID")

    @staticmethod
    def _normalize_language(value: str) -> str:
        """校验并规范化 BCP 47 常用写法；und 表示未指定。"""

        raw = value.strip()
        if raw.lower() == "und":
            return "und"
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", raw):
            raise ValueError(f"无效语言代码: {value}")
        parts = raw.split("-")
        normalized = [parts[0].lower()]
        for part in parts[1:]:
            if len(part) == 4 and part.isalpha():
                normalized.append(part.title())
            elif len(part) == 2 and part.isalpha():
                normalized.append(part.upper())
            else:
                normalized.append(part.lower())
        return "-".join(normalized)
