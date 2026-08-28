"""复核反馈调优建议（T21 P1）：从人工判定样本生成可解释的 Profile 调整草案。

设计原则：

- 只建议、不生效：产物是 DRAFT 草案 + 证据，必须人工确认并完成 Golden
  回归后才允许发布（契约 §12：阈值变更须附 Golden 结果）；
- 证据驱动：数值阈值建议要求误报与确认样本的"门控指标"（契约 §6.4：
  阈值判断所使用的数值必须写入 metrics）存在干净分离窗口；
- 阈值归属：所有调整仍落在 RuleProfile 的 thresholds / severity_overrides，
  不引入任何散落阈值；
- 已知无杠杆的类型（如 invisible_text 的同色分支、number_mismatch 的
  任意差异触发）只产出严重度降级建议，不做伪阈值建议。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import Field

from document_qa.profiles import RuleProfile
from document_qa.schemas.common import SchemaModel
from document_qa.schemas.issue import Severity

# 误报样本数下限：单条误报属于个案，不足以支撑统计性建议。
MIN_FP_SAMPLES = 2
# 严重度降级建议的门槛：已归因判定数与误报率下限。
SEVERITY_MIN_REVIEWED = 3
SEVERITY_MIN_FP_RATE = 0.7
# 无确认样本时的外推步长（比例类阈值的保守增量）。
_THRESHOLD_MARGIN = 0.02
# 干净分离窗口的最小宽度：低于该值的间隔视为重叠，不产生阈值建议。
_MIN_GAP = 0.01

_SEVERITY_ORDER = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


class FeedbackSample(SchemaModel):
    """一条已归因的人工判定样本（指标取自报告 Issue 的 metrics）。"""

    issue_type: str
    detector: str = ""
    severity: str = ""
    # confirmed / false_positive / ignored；ignored 不参与建议计算。
    decision: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class MetricSummary(SchemaModel):
    """门控指标在样本组内的分布摘要。"""

    count: int = 0
    min: float | None = None
    max: float | None = None


class TuningSuggestion(SchemaModel):
    """一条可解释的调优建议。"""

    issue_type: str
    # "threshold"（数值阈值调整）或 "severity"（严重度降级覆盖）。
    kind: str
    # 调整落点：thresholds.<field> 或 severity_overrides.<issue_type>。
    field: str
    current_value: float | str | None = None
    proposed_value: float | str | None = None
    fp_samples: int = 0
    confirmed_samples: int = 0
    fp_metric: MetricSummary = Field(default_factory=MetricSummary)
    confirmed_metric: MetricSummary = Field(default_factory=MetricSummary)
    rationale: str = ""


class TuningAdvice(SchemaModel):
    """一轮调优建议的完整产物：草案 + 全部证据。"""

    base_reference: str
    # "stored" 表示基准来自已保存的 Profile 版本；"default" 为回退内置配置。
    profile_basis: str = "stored"
    sample_count: int = 0
    # 因报告重跑无法归因的决策数（与归因统计口径一致）。
    unmatched: int = 0
    suggestions: list[TuningSuggestion] = Field(default_factory=list)
    # 应用全部建议后的 RuleProfile JSON（version+1、status=draft），可直接保存。
    proposed_profile: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)


class _ThresholdSpec:
    """Issue 类型 → 数值阈值杠杆的映射（只收录确有门控指标的类型）。"""

    def __init__(
        self,
        field: str,
        extractor: Callable[[Mapping[str, Any]], float | None],
        low: float,
        high: float,
        # "above"：指标 > 阈值才触发，排除误报需上调阈值。
        # magnitude 为真时提取器给出绝对值幅度（如字号缩小），落盘时取负号。
        magnitude: bool = False,
        # 严重度分档的上级阈值字段（如 severely_shifted_ratio）：建议值必须
        # 保持在其之下，否则 RuleProfile 的次序校验会拒绝草案。
        cap_field: str | None = None,
    ) -> None:
        self.field = field
        self.extractor = extractor
        self.low = low
        self.high = high
        self.magnitude = magnitude
        self.cap_field = cap_field

    def upper_bound(self, base_profile: RuleProfile) -> float:
        """返回本次建议允许的阈值上限（含严重度分档次序约束）。"""

        cap = self.high
        if self.cap_field:
            companion = getattr(base_profile.detectors.thresholds, self.cap_field)
            cap = min(cap, companion - 0.005)
        return cap


def _shift_value(metrics: Mapping[str, Any]) -> float | None:
    """偏移检测的门控指标：两轴位移比例的绝对值最大者。"""
    x, y = metrics.get("x_shift_ratio"), metrics.get("y_shift_ratio")
    values = [abs(float(v)) for v in (x, y) if isinstance(v, (int, float))]
    return max(values) if values else None


def _metric_value(key: str) -> Callable[[Mapping[str, Any]], float | None]:
    """按 metrics 键取数值的通用提取器。"""

    def extract(metrics: Mapping[str, Any]) -> float | None:
        value = metrics.get(key)
        return abs(float(value)) if isinstance(value, (int, float)) else None

    return extract


# 只收录"指标数值决定是否触发"的类型；同色白字（同色分支无阈值）、
# 数字不一致（任意差异即触发）等不在此列，走严重度建议。
_THRESHOLD_SPECS: dict[str, _ThresholdSpec] = {
    "region_shifted": _ThresholdSpec(
        "shifted_ratio", _shift_value, 0.0, 1.0, cap_field="severely_shifted_ratio"
    ),
    "region_resized": _ThresholdSpec(
        "region_resize_ratio", _metric_value("resize_magnitude"), 0.0, 1.0
    ),
    "typography_changed": _ThresholdSpec(
        "font_grow_ratio", _metric_value("font_size_change_ratio"), 0.0, 2.0
    ),
    "font_shrink": _ThresholdSpec(
        "font_shrink_ratio",
        _metric_value("font_size_change_ratio"),
        0.0,
        1.0,
        magnitude=True,
    ),
    "text_overlap": _ThresholdSpec(
        "overlap_increase_ratio", _metric_value("overlap_increase_ratio"), 0.0, 1.0
    ),
}


def _summary(values: Sequence[float]) -> MetricSummary:
    return MetricSummary(
        count=len(values), min=min(values) if values else None, max=max(values) if values else None
    )


def _threshold_suggestion(
    issue_type: str,
    spec: _ThresholdSpec,
    base_profile: RuleProfile,
    fp_values: list[float],
    confirmed_values: list[float],
) -> TuningSuggestion | None:
    """尝试生成数值阈值建议；无干净窗口或数据不足时返回 None。"""

    if len(fp_values) < MIN_FP_SAMPLES:
        return None
    current = getattr(base_profile.detectors.thresholds, spec.field)
    fp_max = max(fp_values)
    cap = spec.upper_bound(base_profile)
    # 阈值上限（含严重度分档次序）仍无法覆盖最大误报指标：数值杠杆对该类
    # 误报失效（如 resize 幅度 1.24 > 上限 1.0），宁可不给建议也不给过滤
    # 不掉的假建议。
    if not confirmed_values and fp_max >= cap:
        return None
    # 有确认样本时，安全窗口是 (误报最大值, 确认最小值)；窗口不存在即重叠，
    # 说明阈值无法在不误伤真实问题的前提下过滤误报，转严重度建议。
    if confirmed_values:
        confirmed_min = min(confirmed_values)
        window_hi = min(confirmed_min, cap)
        if window_hi - fp_max < _MIN_GAP:
            return None
        proposed = fp_max + (window_hi - fp_max) / 2
    else:
        proposed = fp_max + _THRESHOLD_MARGIN
    # 幅度先夹取到 Schema 边界内，再按符号约定还原（缩小类阈值为负数）；
    # 取整到 4 位小数，避免中点计算把浮点尾数写进配置。
    magnitude_value = round(min(max(proposed, spec.low), cap), 4)
    field_value = -magnitude_value if spec.magnitude else magnitude_value
    if (field_value >= current) if spec.magnitude else (field_value <= current):
        # 建议不比当前阈值更宽松（缩小类为更不负），无改善意义。
        return None

    current_text = f"{current:+.3f}" if spec.magnitude else f"{current:.3f}"
    if confirmed_values:
        direction = f"阈值调整为 {field_value:+.3f}" if spec.magnitude else f"阈值上调至 {field_value:.3f}"
        rationale = (
            f"误报样本门控指标最大 {fp_max:.3f}，确认样本最小 {min(confirmed_values):.3f}，"
            f"存在干净分离窗口；建议{direction}，可过滤全部已知误报"
            "并保留全部已确认问题。"
        )
    else:
        direction = f"建议阈值调整为 {field_value:+.3f}" if spec.magnitude else f"建议阈值上调至 {field_value:.3f}"
        rationale = (
            f"{len(fp_values)} 条误报的门控指标最大 {fp_max:.3f}，超过当前阈值 {current_text}；"
            f"{direction}。当前没有已确认样本佐证，发布前务必运行 Golden 回归并抽查是否误伤真实问题。"
        )
    return TuningSuggestion(
        issue_type=issue_type,
        kind="threshold",
        field=f"thresholds.{spec.field}",
        current_value=current,
        proposed_value=field_value,
        fp_samples=len(fp_values),
        confirmed_samples=len(confirmed_values),
        fp_metric=_summary(fp_values),
        confirmed_metric=_summary(confirmed_values),
        rationale=rationale,
    )


def _severity_suggestion(
    issue_type: str,
    base_profile: RuleProfile,
    fp_count: int,
    confirmed_count: int,
    sample_severity: str,
) -> TuningSuggestion | None:
    """误报占绝对多数且无阈值杠杆时，建议严重度降一档。"""

    reviewed = fp_count + confirmed_count
    if reviewed < SEVERITY_MIN_REVIEWED or fp_count / reviewed < SEVERITY_MIN_FP_RATE:
        return None
    try:
        current = Severity(sample_severity)
    except ValueError:
        return None
    order = _SEVERITY_ORDER.index(current)
    if order <= _SEVERITY_ORDER.index(Severity.LOW):
        return None
    proposed = _SEVERITY_ORDER[order - 1]
    override = base_profile.detectors.severity_overrides.get(issue_type)
    # 已有同档或更低的人工覆盖时不重复建议，尊重既有决策。
    if override is not None and _SEVERITY_ORDER.index(override) <= order - 1:
        return None
    return TuningSuggestion(
        issue_type=issue_type,
        kind="severity",
        field=f"severity_overrides.{issue_type}",
        current_value=str(current),
        proposed_value=str(proposed),
        fp_samples=fp_count,
        confirmed_samples=confirmed_count,
        rationale=(
            f"{reviewed} 条判定中 {fp_count} 条误报（误报率 {fp_count / reviewed:.0%}），"
            f"且无干净的阈值分离窗口；建议将该类型严重度从 {current} 降为 {proposed}，"
            "减少误报对文档评分与 PASS/FAIL 判定的影响。"
        ),
    )


def suggest_tuning(
    base_profile: RuleProfile,
    base_reference: str,
    samples: Sequence[FeedbackSample],
    *,
    unmatched: int = 0,
) -> TuningAdvice:
    """从人工判定样本生成调优建议与 DRAFT 草案；纯函数，不落任何存储。"""

    advice = TuningAdvice(base_reference=base_reference, sample_count=len(samples), unmatched=unmatched)
    grouped: dict[str, dict[str, list[FeedbackSample]]] = {}
    for sample in samples:
        if sample.decision == "ignored":
            continue
        grouped.setdefault(sample.issue_type, {}).setdefault(sample.decision, []).append(sample)

    suggestions: list[TuningSuggestion] = []
    for issue_type, buckets in sorted(grouped.items()):
        fp_samples = buckets.get("false_positive", [])
        confirmed_samples = buckets.get("confirmed", [])
        spec = _THRESHOLD_SPECS.get(issue_type)
        suggestion: TuningSuggestion | None = None
        if spec is not None:
            fp_values = [v for v in map(spec.extractor, (s.metrics for s in fp_samples)) if v is not None]
            confirmed_values = [
                v for v in map(spec.extractor, (s.metrics for s in confirmed_samples)) if v is not None
            ]
            suggestion = _threshold_suggestion(
                issue_type, spec, base_profile, fp_values, confirmed_values
            )
        if suggestion is None and fp_samples:
            suggestion = _severity_suggestion(
                issue_type,
                base_profile,
                len(fp_samples),
                len(confirmed_samples),
                fp_samples[0].severity,
            )
        if suggestion is not None:
            suggestions.append(suggestion)

    advice.suggestions = suggestions
    if suggestions:
        advice.proposed_profile = _apply_suggestions(base_profile, suggestions)
        advice.notes.append(
            "草案为 DRAFT 版本，保存并发布前请完成 Golden 回归"
            "（document-qa CLI 对 examples/ 样例或 tests/test_golden_samples.py）。"
        )
    if base_profile.language_overrides:
        advice.notes.append("基准 Profile 含 language_overrides，本草案仅调整全局 detectors 配置。")
    return advice


def _apply_suggestions(
    base_profile: RuleProfile, suggestions: Sequence[TuningSuggestion]
) -> dict[str, Any]:
    """把建议应用到基准 Profile 的深拷贝上，输出经 Schema 校验的 DRAFT JSON。"""

    data = base_profile.model_dump(mode="json")
    detectors = data["detectors"]
    for suggestion in suggestions:
        if suggestion.kind == "threshold":
            field = suggestion.field.removeprefix("thresholds.")
            detectors["thresholds"][field] = suggestion.proposed_value
        else:
            issue_type = suggestion.field.removeprefix("severity_overrides.")
            detectors["severity_overrides"][issue_type] = suggestion.proposed_value
    data["version"] = data.get("version", 1) + 1
    data["status"] = "draft"
    # 重新走一遍 Schema 校验：保证草案必然是合法 RuleProfile（边界/枚举兜底）。
    return RuleProfile.model_validate(data).model_dump(mode="json")
