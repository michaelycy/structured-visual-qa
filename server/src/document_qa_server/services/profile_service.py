"""Profile 服务：基于 SQLite 的版本化规则配置生命周期管理。"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from dataclasses import dataclass
from pathlib import Path

from document_qa.profiles import (
    ProfileStatus,
    RuleProfile,
    RuleProfileStore,
    default_rule_profile,
)
from document_qa_server.persistence import Database


@dataclass(frozen=True)
class ProfileSummary:
    """列表项：标识、名称、版本与状态，不含完整配置。"""

    filename: str
    profile_id: str
    name: str
    version: int
    status: str
    reference: str


class ProfileService:
    """封装规则配置的校验、版本保存、查询与归档。"""

    def __init__(self, *, artifacts_dir: Path, database: Database | None = None) -> None:
        """注入 SQLite；首次启动幂等导入旧 profiles/*.json。"""

        self._database = database or Database(artifacts_dir=artifacts_dir)
        self._legacy_dir = artifacts_dir / "profiles"
        # 内置默认配置随 Schema 演进原位补齐；用户发布版本仍保持不可覆盖。
        self._save_validated(default_rule_profile(), allow_published_upgrade=True)
        self._import_legacy()
        self._clean_stored_profiles()

    @staticmethod
    def default() -> RuleProfile:
        """返回内置平衡配置，作为配置表单初始值。"""

        return default_rule_profile()

    @staticmethod
    def schema() -> dict:
        """返回 Profile JSON Schema，供前端动态生成表单。"""

        return RuleProfile.model_json_schema()

    def load(self, path: Path) -> RuleProfile:
        """兼容服务器外部路径配置；文件仍通过核心 Store 严格校验。"""

        return RuleProfileStore.load(path)

    def save(self, profile_data: dict) -> tuple[str, str]:
        """校验并保存草稿版本，返回数据库定位符与版本引用。"""

        validated = RuleProfile.model_validate(profile_data)
        if validated.status != ProfileStatus.DRAFT:
            raise ValueError("规则保存只接受草稿；请通过发布接口变更状态")
        filename = self._save_validated(validated)
        return f"sqlite:{filename}", validated.reference

    def list(self) -> list[ProfileSummary]:
        """列出未归档的自定义 Profile；内置默认值由 default 接口提供。"""

        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT filename, profile_id, name, version, status "
                "FROM rule_profile_versions "
                "WHERE status <> 'archived' AND filename <> ? ORDER BY filename",
                (self._filename(default_rule_profile()),),
            ).fetchall()
        return [
            ProfileSummary(
                filename=row["filename"],
                profile_id=row["profile_id"],
                name=row["name"],
                version=row["version"],
                status=row["status"],
                reference=f"{row['profile_id']}@{row['version']}",
            )
            for row in rows
        ]

    def get(self, filename: str) -> RuleProfile:
        """按兼容文件名读取配置，包括已归档的历史版本。"""

        self._validate_filename(filename)
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM rule_profile_versions WHERE filename = ?",
                (filename,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Profile 不存在: {filename}")
        return RuleProfile.model_validate_json(row["payload_json"])

    def delete(self, filename: str) -> None:
        """归档自定义 Profile；历史对比仍可通过版本外键复现。"""

        self._validate_filename(filename)
        if filename == self._filename(default_rule_profile()):
            raise ValueError("内置默认 Profile 不可归档")
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT payload_json, status FROM rule_profile_versions WHERE filename = ?",
                (filename,),
            ).fetchone()
            if row is None or row["status"] == ProfileStatus.ARCHIVED.value:
                raise ValueError(f"Profile 不存在: {filename}")
            archived = RuleProfile.model_validate_json(row["payload_json"]).model_copy(
                update={"status": ProfileStatus.ARCHIVED}
            )
            payload = archived.model_dump_json()
            connection.execute(
                "UPDATE rule_profile_versions SET status = ?, payload_json = ?, "
                "payload_sha256 = ?, updated_at = ? WHERE filename = ?",
                (
                    ProfileStatus.ARCHIVED.value,
                    payload,
                    hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    Database.now(),
                    filename,
                ),
            )

    def publish(self, filename: str) -> ProfileSummary:
        """把草稿发布为不可覆盖版本；已发布时幂等返回。"""

        self._validate_filename(filename)
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json, status FROM rule_profile_versions WHERE filename = ?",
                (filename,),
            ).fetchone()
        if row is None or row["status"] == ProfileStatus.ARCHIVED.value:
            raise ValueError(f"Profile 不存在: {filename}")
        profile = RuleProfile.model_validate_json(row["payload_json"])
        if profile.status != ProfileStatus.PUBLISHED:
            profile = profile.model_copy(update={"status": ProfileStatus.PUBLISHED})
            self._save_validated(profile)
        return ProfileSummary(
            filename=filename,
            profile_id=profile.profile_id,
            name=profile.name,
            version=profile.version,
            status=ProfileStatus.PUBLISHED.value,
            reference=profile.reference,
        )

    def _save_validated(
        self,
        profile: RuleProfile,
        *,
        allow_published_upgrade: bool = False,
    ) -> str:
        """以家族+版本 upsert；完整 JSON 与摘要在同一事务更新。"""

        filename = self._filename(profile)
        payload = profile.model_dump_json()
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = Database.now()
        with self._database.transaction() as connection:
            existing = connection.execute(
                "SELECT status, payload_sha256 FROM rule_profile_versions "
                "WHERE profile_id = ? AND version = ?",
                (profile.profile_id, profile.version),
            ).fetchone()
            if existing is not None:
                if existing["status"] == ProfileStatus.PUBLISHED.value:
                    if existing["payload_sha256"] == digest:
                        return filename
                    if allow_published_upgrade:
                        pass
                    else:
                        raise ValueError(
                            f"已发布规则版本不可覆盖: {profile.reference}；请创建新版本"
                        )
                elif existing["status"] == ProfileStatus.ARCHIVED.value:
                    raise ValueError(
                        f"已归档规则版本不可复用: {profile.reference}；请创建新版本"
                    )
            connection.execute(
                "INSERT INTO rule_profile_versions("
                "profile_id, version, filename, name, status, description, payload_json, "
                "payload_sha256, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(profile_id, version) DO UPDATE SET "
                "filename=excluded.filename, name=excluded.name, status=excluded.status, "
                "description=excluded.description, payload_json=excluded.payload_json, "
                "payload_sha256=excluded.payload_sha256, updated_at=excluded.updated_at",
                (
                    profile.profile_id,
                    profile.version,
                    filename,
                    profile.name,
                    profile.status.value,
                    profile.description,
                    payload,
                    digest,
                    now,
                    now,
                ),
            )
        return filename

    def _import_legacy(self) -> None:
        """幂等导入旧 JSON；非法文件保留原状并跳过。"""

        import_key = "profiles_json_v1"
        if self._database.legacy_import_done(import_key):
            return
        paths = sorted(self._legacy_dir.glob("*.json")) if self._legacy_dir.is_dir() else []
        imported = 0
        for path in paths:
            try:
                self._save_validated(
                    RuleProfile.model_validate(
                        self._merge_legacy_profile(
                            json.loads(path.read_text(encoding="utf-8"))
                        )
                    )
                )
                imported += 1
            except Exception:
                continue
        self._database.mark_legacy_import(
            import_key, source_count=len(paths), imported_count=imported
        )

    def _clean_stored_profiles(self) -> int:
        """幂等补齐旧规则缺失字段，并保持版本身份和历史引用不变。

        数据库摘要列是列表与外键使用的权威身份；旧 payload 只提供规则值。
        Schema 新增字段从当前默认配置补齐，已有自定义值始终优先保留。
        """

        cleaned = 0
        defaults = default_rule_profile().model_dump(mode="json")
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT profile_id, version, filename, name, status, description, "
                "payload_json, payload_sha256 FROM rule_profile_versions"
            ).fetchall()
            for row in rows:
                try:
                    legacy = json.loads(row["payload_json"])
                    merged = self._merge_profile_values(defaults, legacy)
                    merged.update(
                        {
                            "profile_id": row["profile_id"],
                            "version": row["version"],
                            "name": row["name"],
                            "status": row["status"],
                            "description": row["description"],
                        }
                    )
                    validated = RuleProfile.model_validate(merged)
                except Exception as exc:
                    raise ValueError(
                        f"旧规则数据无法清洗: {row['filename']}: {exc}"
                    ) from exc
                payload = validated.model_dump_json()
                digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                if digest == row["payload_sha256"]:
                    continue
                connection.execute(
                    "UPDATE rule_profile_versions SET payload_json = ?, "
                    "payload_sha256 = ?, updated_at = ? WHERE filename = ?",
                    (payload, digest, Database.now(), row["filename"]),
                )
                cleaned += 1
        return cleaned

    @staticmethod
    def _filename(profile: RuleProfile) -> str:
        """生成兼容旧 API 的规则版本文件名。"""

        return f"{profile.profile_id}-v{profile.version}.json"

    @staticmethod
    def _merge_legacy_profile(legacy: dict[str, Any]) -> dict[str, Any]:
        """递归补齐后续新增字段，保留旧配置已经明确设置的值。"""

        return ProfileService._merge_profile_values(
            default_rule_profile().model_dump(mode="json"), legacy
        )

    @staticmethod
    def _merge_profile_values(
        defaults: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        """递归合并规则值；嵌套对象补缺，显式旧值覆盖默认值。"""

        def merge(defaults: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
            result = dict(defaults)
            for key, value in values.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merge(result[key], value)
                else:
                    result[key] = value
            return result

        return merge(defaults, values)

    @staticmethod
    def _validate_filename(filename: str) -> None:
        """拒绝路径分隔和上级路径，保持 API 输入安全。"""

        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("无效 Profile 文件名")
