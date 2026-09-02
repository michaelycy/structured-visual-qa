"""渲染验证服务：按页裁决候选 Issue 并输出证据事件（T38 阶段 1）。

阶段 1 只注册 invisible_text（P0）。服务是纯裁决器：不修改 Issue、
不产生新 Issue；裁决结果以 dict 事件返回，由管线经 progress 通道
输出（shadow 不改变任何检测输出）。
"""

from pathlib import Path
from typing import Any

from document_qa.verification.pixel_contrast import verify_invisible_text
from document_qa.verification.pixel_out_of_page import verify_content_out_of_page
from document_qa.profiles import VerificationSettings
from document_qa.renderers.pymupdf_renderer import PyMuPDFRenderer
from document_qa.schemas import Issue, Page, Severity


class VerificationService:
    """对一页的候选 Issue 执行渲染实证。"""

    def __init__(self, settings: VerificationSettings | None = None) -> None:
        """注入验证配置；缺省使用 Profile 内置默认值（shadow）。"""

        self.settings = settings or VerificationSettings()

    def verify_page(
        self,
        *,
        issues: list[Issue],
        target_page: Page,
        target_path: Path,
        target_password: str | None,
        renderer: PyMuPDFRenderer,
    ) -> list[dict[str, Any]]:
        """裁决一页内已注册类型的 Issue，返回证据事件列表。

        事件仅包含有实质裁决的条目（confirmed/rejected）；fail-open
        原则下渲染失败等异常按 confirmed 处理并注明原因，验证层的
        任何故障都不改变检测输出。
        """

        candidates = [
            issue
            for issue in issues
            if issue.bbox is not None
            and issue.type.value in ("invisible_text", "content_out_of_page")
        ]
        if not candidates:
            return []
        events: list[dict[str, Any]] = []
        page_pixels: tuple[int, int, bytes] | None = None
        for issue in candidates[: self.settings.max_issues_per_page]:
            try:
                if page_pixels is None:
                    page_pixels = renderer.page_pixels(
                        target_path,
                        page=target_page.page,
                        dpi=self.settings.dpi,
                        password=target_password,
                    )
                if issue.type.value == "invisible_text":
                    outcome = verify_invisible_text(
                        issue,
                        target_page=target_page,
                        page_pixels=page_pixels,
                        settings=self.settings,
                    )
                else:
                    outcome = verify_content_out_of_page(
                        issue,
                        page_width=target_page.width,
                        page_height=target_page.height,
                        page_pixels=page_pixels,
                        settings=self.settings,
                    )
            except Exception as exc:
                # fail-open：验证层故障不能吞掉真实问题，维持原判。
                outcome = {
                    "verdict": "confirmed",
                    "reason": "verifier_error",
                    "error": type(exc).__name__,
                    "method": "pixel_contrast",
                    "dpi": self.settings.dpi,
                }
            events.append({"issue_id": issue.id, **outcome})
        return events


def apply_enforce_decisions(
    issues: list[Issue],
    events: list[dict[str, Any]],
    enforce_types: set[str],
) -> None:
    """把 enforce 裁决作用于 Issue（原位替换，仅 enforce 模式调用）。

    rejected 且类型在 enforce_types 内：严重度降 INFO、描述追加实证
    结论（保留可解释性，不删除——验收人能看到系统看过并否决了什么）；
    全部已验证 Issue 的证据写入 metrics。类型不在清单内的只落证据。
    """

    events_by_id = {event["issue_id"]: event for event in events}
    for index, issue in enumerate(issues):
        event = events_by_id.get(issue.id)
        if event is None:
            continue
        # 计时字段只进事件通道（shadow 排查用），不进 metrics——
        # 报告必须逐字节可复现，计时抖动会破坏这一前提。
        evidence = {k: v for k, v in event.items() if k != "duration_ms"}
        metrics = dict(issue.metrics)
        metrics["verification"] = evidence
        if event.get("verdict") == "rejected" and issue.type.value in enforce_types:
            issues[index] = issue.model_copy(
                update={
                    "severity": Severity.INFO,
                    "description": (
                        f"{issue.description}"
                        "（渲染实证否定：文字与背景对比度"
                        f" {event.get('text_pixel_contrast')} ≥ 阈值"
                        f" {event.get('threshold_used')}，详见 metrics。"
                        "定级已降为 INFO，人工复核请以渲染图为准。）"
                    ),
                    "metrics": metrics,
                }
            )
        else:
            issues[index] = issue.model_copy(update={"metrics": metrics})
