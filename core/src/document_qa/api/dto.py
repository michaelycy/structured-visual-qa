"""API 层的请求/响应 DTO。

与核心 schemas/（数据契约）刻意分离：HTTP 契约的演化不应迫使核心
模型变更，反之亦然。字段命名与 CLI 参数保持一致降低心智成本。
"""

from typing import Literal

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    """一次比较任务的输入：本地路径 + 可选 Profile。"""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    profile_path: str | None = None
    render: bool = True
    render_scope: Literal["all", "issues"] = "issues"


class VerifyRequest(BaseModel):
    """分阶段验证任务输入：执行到指定阶段为止。"""

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    stop_after: Literal[
        "parse", "group", "alignment", "match", "detect", "report"
    ] = "report"


class ProfileSaveRequest(BaseModel):
    """界面提交的完整 Profile 对象；具体字段由核心模型校验。"""

    profile: dict
