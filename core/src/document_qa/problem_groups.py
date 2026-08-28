"""把细粒度规则命中汇总为面向用户的问题组。"""

from document_qa.schemas import Issue, IssueType, PageQAResult
from document_qa.text_visibility import has_visible_text


_RASTER_LAYER_DUPLICATE_TYPES = frozenset(
    {
        IssueType.REGION_SHIFTED,
        IssueType.REGION_RESIZED,
        IssueType.TEXT_FRAGMENTED,
        IssueType.FONT_SHRINK,
        IssueType.TYPOGRAPHY_CHANGED,
        IssueType.TEXT_ALIGNMENT_CHANGED,
    }
)


def count_problem_groups(pages: list[PageQAResult]) -> int:
    """统计根因问题组，保留 Issue 明细但避免把同一异常重复展示为多个问题。"""

    total = 0
    for page in pages:
        rasterized_text_ids = {
            region_id
            for issue in page.issues
            if issue.type == IssueType.TEXT_RASTERIZED
            for region_id in [issue.metrics.get("invisible_text_region")]
            if isinstance(region_id, str) and region_id
        }
        groups: set[tuple[int, str, str]] = set()
        for issue in page.issues:
            if _is_noise_issue(issue, rasterized_text_ids):
                continue
            if issue.type == IssueType.TEXT_RASTERIZED:
                # 同页大量文字同时转为图片通常来自一次导出策略，而非几十个独立根因。
                groups.add((page.page, "systemic", issue.type.value))
            elif issue.source_region:
                groups.add((page.page, "source", issue.source_region))
            elif issue.target_region:
                groups.add((page.page, "target", issue.target_region))
            else:
                groups.add((page.page, "issue", issue.id))
        total += len(groups)
    return total


def _is_noise_issue(issue: Issue, rasterized_text_ids: set[str]) -> bool:
    """识别历史报告中已知的空白对象和栅格化透明层重复命中。"""

    if issue.type == IssueType.ADDED_ELEMENT and _blank_metric_text(
        issue.metrics.get("target_text")
    ):
        return True
    if issue.type == IssueType.TEXT_OVERLAP and (
        _blank_metric_text(issue.metrics.get("primary_text"))
        or _blank_metric_text(issue.metrics.get("other_text"))
    ):
        return True
    return (
        issue.type in _RASTER_LAYER_DUPLICATE_TYPES
        and issue.target_region in rasterized_text_ids
    )


def _blank_metric_text(value: object) -> bool:
    """只把明确存在且全为空白的文本判为噪声，缺失证据不作推断。"""

    return isinstance(value, str) and not has_visible_text(value)
