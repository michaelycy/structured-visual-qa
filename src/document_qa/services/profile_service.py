"""Profile 服务：加载默认配置、导出 Schema、校验并保存编辑结果。"""

from __future__ import annotations

from pathlib import Path

from document_qa.profiles import RuleProfile, RuleProfileStore, default_rule_profile


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
        path = RuleProfileStore.save(validated, self._profiles_dir / filename)
        return path, validated.reference
