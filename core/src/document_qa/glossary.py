"""术语库模型与内置示例。

术语库与 RuleProfile 分离：阈值是行为配置，术语是业务资产，两者的
版本节奏和审批流程不同。两者共同点是完全版本化、可被报告快照引用。
"""

from __future__ import annotations

from pydantic import Field, model_validator

from document_qa.schemas.common import SchemaModel


class GlossaryEntry(SchemaModel):
    """一条术语：源语言写法与允许的目标译法集合。"""

    term: str = Field(min_length=1, max_length=200)
    # 允许译法列表；目标文本命中任一即合规。
    translations: list[str] = Field(min_length=1)
    # 可选业务备注（如"客户 2024-08 指定译法"）。
    note: str = ""
    # 区分大小写匹配（默认关闭：中英术语混排时大小写漂移常见）。
    case_sensitive: bool = False


class Glossary(SchemaModel):
    """一次 QA 任务可引用的版本化术语库。"""

    schema_version: int = Field(default=1, ge=1)
    glossary_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)
    description: str = ""
    entries: list[GlossaryEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_terms(self) -> "Glossary":
        """术语源写法必须唯一，否则违规归属无法确定。"""

        terms = [entry.term for entry in self.entries]
        if len(terms) != len(set(terms)):
            duplicated = {t for t in terms if terms.count(t) > 1}
            raise ValueError(f"术语重复: {sorted(duplicated)}")
        return self

    @property
    def reference(self) -> str:
        """返回适合报告和界面显示的稳定版本引用。"""

        return f"{self.glossary_id}@{self.version}"


def default_glossary() -> Glossary:
    """返回内置示例术语库（中英对照），作为界面起步与测试基线。"""

    return Glossary(
        glossary_id="un-demo",
        name="示例术语库（国际组织常用）",
        version=1,
        description="内置演示用术语库；生产环境应创建业务专属术语库。",
        entries=[
            GlossaryEntry(
                term="United Nations",
                translations=["联合国"],
                note="机构全称",
            ),
            GlossaryEntry(
                term="sustainable development",
                translations=["可持续发展"],
            ),
            GlossaryEntry(
                term="gross domestic product",
                translations=["国内生产总值", "GDP"],
                note="允许两种译法",
            ),
            GlossaryEntry(
                term="World Health Organization",
                translations=["世界卫生组织", "世卫组织"],
            ),
        ],
    )
