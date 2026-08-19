"""Profile 服务：规则配置的完整生命周期管理。

能力覆盖：内置默认值、JSON Schema、列表、读取、校验保存与删除。
所有界面保存的 Profile 落在 profiles/ 子目录，文件名由 profile_id
与版本组成，删除按同一命名规则定位，不接受任意路径。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from document_qa.profiles import RuleProfile, RuleProfileStore, default_rule_profile
from document_qa_server.services.filelock import file_lock


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
    """封装规则配置在界面场景下的读写。"""

    def __init__(self, *, artifacts_dir: Path) -> None:
        """注入产物根目录；界面保存的 Profile 写入其 profiles/ 子目录。"""

        self._profiles_dir = artifacts_dir / "profiles"

    @staticmethod
    def default() -> RuleProfile:
        """返回内置平衡配置，作为配置表单初始值。"""

        return default_rule_profile()

    @staticmethod
    def schema() -> dict:
        """返回 Profile JSON Schema，供前端动态生成表单。"""

        return RuleProfile.model_json_schema()

    def load(self, path: Path) -> RuleProfile:
        """加载并严格校验外部 Profile 文件。

        路径不存在或校验失败抛出 ValueError，由 API 层转换状态码。
        """

        return RuleProfileStore.load(path)

    def save(self, profile_data: dict) -> tuple[Path, str]:
        """校验并原子保存界面提交的 Profile，返回路径与版本引用。"""

        validated = RuleProfile.model_validate(profile_data)
        filename = f"{validated.profile_id}-v{validated.version}.json"
        with file_lock(self._profiles_dir / ".lock"):
            path = RuleProfileStore.save(validated, self._profiles_dir / filename)
        return path, validated.reference

    def list(self) -> list[ProfileSummary]:
        """列出已保存的全部 Profile，按文件名排序。"""

        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        summaries: list[ProfileSummary] = []
        for path in sorted(self._profiles_dir.glob("*.json")):
            try:
                profile = RuleProfile.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                # 历史遗留的非法文件跳过而不是让整个列表失败。
                continue
            summaries.append(
                ProfileSummary(
                    filename=path.name,
                    profile_id=profile.profile_id,
                    name=profile.name,
                    version=profile.version,
                    status=profile.status.value,
                    reference=profile.reference,
                )
            )
        return summaries

    def get(self, filename: str) -> RuleProfile:
        """按文件名读取单个已保存 Profile；文件名必须不含路径分隔。"""

        path = self._safe_path(filename)
        if not path.is_file():
            raise ValueError(f"Profile 不存在: {filename}")
        return RuleProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, filename: str) -> None:
        """删除已保存 Profile；内置默认配置不在磁盘上，无法误删。"""

        path = self._safe_path(filename)
        with file_lock(self._profiles_dir / ".lock"):
            if not path.is_file():
                raise ValueError(f"Profile 不存在: {filename}")
            path.unlink()

    def _safe_path(self, filename: str) -> Path:
        """约束文件名只含安全字符，防止路径穿越（契约 §9）。"""

        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("无效 Profile 文件名")
        return self._profiles_dir / filename
