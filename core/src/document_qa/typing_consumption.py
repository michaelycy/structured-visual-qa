"""类型消费矩阵（T39 阶段 3）：按语义类型裁决 Issue 的豁免与降级。

矩阵配置在 RuleProfile.typing.consumption（键 "issue类型:语义类型"，
值 normal / downgraded / exempt）。设计依据：翻译场景下图表标签
重排、公式排版变化、页眉页脚位移属常态而非缺陷——但豁免是漏报
窗口，因此矩阵逐格独立可配，且只对带目标区域、且该区域有高/中
置信类型标签的 Issue 生效；无标签区域一律 normal（退化为现状）。
"""

from document_qa.profiles import TypingSettings
from document_qa.schemas import Issue, Page, Severity


def apply_consumption(
    issues: list[Issue], target_page: Page, settings: TypingSettings
) -> list[Issue]:
    """按消费矩阵过滤/降级 Issue，返回新的 Issue 列表。"""

    if not settings.enabled or not settings.consumption:
        return issues
    regions_by_id = {region.id: region for region in target_page.regions}
    kept: list[Issue] = []
    for issue in issues:
        semantic_type = None
        if issue.target_region:
            region = regions_by_id.get(issue.target_region)
            if region is not None:
                label = region.metadata.get("semantic_type")
                if isinstance(label, dict):
                    semantic_type = label.get("type")
        decision = "normal"
        if semantic_type:
            decision = settings.consumption.get(
                f"{issue.type.value}:{semantic_type}", "normal"
            )
        if decision == "exempt":
            # 豁免：该组合属翻译常态，不作为缺陷产出。
            continue
        if (
            decision == "downgraded"
            and issue.severity.value in ("medium", "high", "critical")
        ):
            # 降级：保留可见性，严重度上限压到 LOW。
            issue = issue.model_copy(update={"severity": Severity.LOW})
        kept.append(issue)
    return kept
