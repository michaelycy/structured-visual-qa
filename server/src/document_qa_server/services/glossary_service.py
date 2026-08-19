"""术语库服务：界面场景下的术语库生命周期管理。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from document_qa.glossary import Glossary, default_glossary


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
    """封装术语库的读写与校验保存。"""

    def __init__(self, *, artifacts_dir: Path) -> None:
        """注入产物根目录；术语库写入 glossaries/ 子目录。"""

        self._glossaries_dir = artifacts_dir / "glossaries"

    @staticmethod
    def default() -> Glossary:
        """返回内置示例术语库，作为界面初始值。"""

        return default_glossary()

    def save(self, data: dict) -> tuple[Path, str]:
        """校验并原子保存术语库，返回路径与版本引用。"""

        validated = Glossary.model_validate(data)
        self._glossaries_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{validated.glossary_id}-v{validated.version}.json"
        path = self._glossaries_dir / filename
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(validated.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
        return path, validated.reference

    def list(self) -> list[GlossarySummary]:
        """列出已保存术语库摘要，按文件名排序。"""

        if not self._glossaries_dir.is_dir():
            return []
        summaries: list[GlossarySummary] = []
        for path in sorted(self._glossaries_dir.glob("*.json")):
            try:
                glossary = Glossary.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                continue  # 非法历史文件跳过
            summaries.append(
                GlossarySummary(
                    filename=path.name,
                    glossary_id=glossary.glossary_id,
                    name=glossary.name,
                    version=glossary.version,
                    entry_count=len(glossary.entries),
                    reference=glossary.reference,
                )
            )
        return summaries

    def get(self, filename: str) -> Glossary:
        """按文件名读取术语库；文件名必须不含路径分隔。"""

        path = self._safe_path(filename)
        if not path.is_file():
            raise ValueError(f"术语库不存在: {filename}")
        return Glossary.model_validate_json(path.read_text(encoding="utf-8"))

    def load_by_reference(self, reference: str) -> Glossary:
        """按版本引用（id@version）加载术语库。"""

        if "@" not in reference:
            raise ValueError(f"无效术语库引用: {reference}")
        glossary_id, version = reference.rsplit("@", 1)
        filename = f"{glossary_id}-v{version}.json"
        return self.get(filename)

    def delete(self, filename: str) -> None:
        """删除已保存术语库。"""

        path = self._safe_path(filename)
        if not path.is_file():
            raise ValueError(f"术语库不存在: {filename}")
        path.unlink()

    def _safe_path(self, filename: str) -> Path:
        """约束文件名只含安全字符，防止路径穿越（契约 §9）。"""

        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("无效术语库文件名")
        return self._glossaries_dir / filename
