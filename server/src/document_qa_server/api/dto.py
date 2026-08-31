"""API 层的请求/响应 DTO。

与核心 schemas/（数据契约）刻意分离：HTTP 契约的演化不应迫使核心
模型变更，反之亦然。字段命名与 CLI 参数保持一致降低心智成本。
"""

from typing import Literal

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    """一次比较任务的输入：本地路径 + 可选 Profile。

    密码字段仅用于打开密码（user password）PDF，只在请求内传递，
    不落历史记录与任何产物。
    """

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    source_display: str = ""
    target_display: str = ""
    profile_path: str | None = None
    glossary_reference: str | None = None
    render: bool = True
    render_scope: Literal["all", "issues"] = "issues"
    source_password: str | None = Field(default=None, max_length=256)
    target_password: str | None = Field(default=None, max_length=256)


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


def review_task_id_for_report(report: dict) -> str:
    """从报告文档对身份派生复核任务 ID。

    派生规则与既有复核记录完全一致（文档 ID 前 12 位以连字符拼接），
    保证历史判定延续；由服务端统一下发后，前端不再自行拼接，
    避免派生规则散落与前后端漂移。
    """

    source = str(report.get("source_document_id") or "")[:12]
    target = str(report.get("target_document_id") or "")[:12]
    return f"{source}-{target}"


def attach_review_task_id(report: dict | None) -> dict | None:
    """在报告负载中注入 review_task_id；原样返回便于内联使用。"""

    if report is None:
        return None
    report["review_task_id"] = review_task_id_for_report(report)
    return report
