"""可供 CLI、API 和后续界面共用的版本化规则配置。"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from document_qa.schemas.common import SchemaModel
from document_qa.schemas.issue import IssueType, Severity


class ProfileStatus(StrEnum):
    """规则配置在版本管理流程中的状态。"""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class MatchingWeights(SchemaModel):
    """控制 Region 匹配分数的各项权重。"""

    position: float = Field(default=0.40, ge=0, le=1)
    size: float = Field(default=0.25, ge=0, le=1)
    type: float = Field(default=0.20, ge=0, le=1)
    order: float = Field(default=0.15, ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> "MatchingWeights":
        """权重必须精确归一化，避免界面输入导致分数范围漂移。"""

        total = self.position + self.size + self.type + self.order
        if abs(total - 1.0) > 1e-6:
            raise ValueError("匹配权重总和必须等于 1")
        return self


class LogicalGroupingSettings(SchemaModel):
    """控制匹配前的视觉文本流规范化。"""

    enabled: bool = True
    max_regions: int = Field(default=8, ge=2, le=50)
    line_gap_ratio: float = Field(default=0.6, ge=0, le=3)
    horizontal_overlap_ratio: float = Field(default=0.3, ge=0, le=1)
    font_size_tolerance_ratio: float = Field(default=0.15, ge=0, le=1)
    edge_tolerance_ratio: float = Field(default=0.015, ge=0, le=0.2)
    counterpart_overlap_ratio: float = Field(default=0.5, ge=0, le=1)


class MatchingSettings(SchemaModel):
    """控制 Region 候选匹配和文本合并容错。"""

    minimum_score: float = Field(default=0.45, ge=0, le=1)
    merged_text_coverage_ratio: float = Field(default=0.40, ge=0, le=1)
    # 文本类 Region 之间的类型相似度（标题/段落/列表可跨语言互配）。
    text_type_similarity: float = Field(default=0.80, ge=0, le=1)
    weights: MatchingWeights = Field(default_factory=MatchingWeights)
    logical_grouping: LogicalGroupingSettings = Field(
        default_factory=LogicalGroupingSettings
    )


class LayoutAnalogWeights(SchemaModel):
    """重叠检测中查找源版面类比（layout analog）的评分权重。

    拓扑对照更重视位置，尺寸只用于区分同位置的多个对象；两项必须
    归一化为凸组合，保持得分范围稳定。
    """

    position: float = Field(default=0.70, ge=0, le=1)
    size: float = Field(default=0.30, ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> "LayoutAnalogWeights":
        """位置与尺寸权重必须精确归一化。"""

        if abs(self.position + self.size - 1.0) > 1e-6:
            raise ValueError("版面类比权重总和必须等于 1")
        return self


class PageAlignmentSettings(SchemaModel):
    """控制跨页对齐：容忍翻译导致的整体移页。"""

    enabled: bool = True
    # 允许参与配对的最大页码差；窗口外相似度不计算也不可配对。
    max_shift: int = Field(default=3, ge=0, le=50)
    # 跳过一页（判定缺失/新增）付出的代价，单位与页相似度一致（0-1）。
    skip_penalty: float = Field(default=0.5, ge=0, le=10)
    # 动态规划对齐比按页码直配每偏离一页需要高出的最小余量，抑制噪声移页。
    shift_margin: float = Field(default=0.01, ge=0, le=10)


class DetectorToggles(SchemaModel):
    """允许配置界面逐项启用或关闭检测器。"""

    missing_element: bool = True
    region_shifted: bool = True
    font_shrink: bool = True
    content_out_of_page: bool = True
    overlap: bool = True
    number_mismatch: bool = True
    untranslated_text: bool = True
    # 对位置尺寸稳定的大图片运行可选 OCR，确认图片内部的局部漏译。
    untranslated_raster_ocr: bool = True
    # 匹配 Region 的宽/高剧变（翻译后段落被合并或拆散）。
    region_resized: bool = True
    # 目标文字被竖排/拆散成单字母碎片（窄列翻译溢出的典型破坏）。
    text_fragmented: bool = True
    # 目标字号明显放大（换行爆炸的前兆；缩小由 font_shrink 负责）。
    font_grow: bool = True
    # 目标文字颜色与页面背景同色（视觉不可见，如白字白底）。
    invisible_text: bool = True
    # 目标使用透明文本层承载可检索内容、同位置图片负责可见渲染。
    text_rasterized: bool = True
    # 段落级水平对齐方式发生变化（如右对齐变左对齐）。
    text_alignment_changed: bool = True


class SeverityBand(SchemaModel):
    """严重度分档：指标值达到 gte 时命中该档。

    分档是"幅度 → 严重度"的映射：轻微幅度 MEDIUM、严重幅度 HIGH，
    替代以往所有命中一律 HIGH 的扁平判定；阈值判断的数值本身仍由
    各检测器的基础阈值（如 untranslated_ratio）先行把关。
    """

    gte: float = Field(ge=0, description="指标值达到该值（≥）时命中本档")
    severity: Severity


# 各检测器的缺省分档：轻微幅度 MEDIUM、严重幅度 HIGH。
# 数值经过真实中英文 PDF 校准（见 docs/manuals/custom-rule-profile.md §7.6）。
def _default_number_bands() -> list[SeverityBand]:
    """数字不一致：差异数 ≥5 为 HIGH，1～4 为 MEDIUM。"""

    return [
        SeverityBand(gte=5, severity=Severity.HIGH),
        SeverityBand(gte=1, severity=Severity.MEDIUM),
    ]


def _default_font_shrink_bands() -> list[SeverityBand]:
    """字号缩小：缩小 ≥40% 为 HIGH，20%～40% 为 MEDIUM（幅度取正数）。"""

    return [
        SeverityBand(gte=0.4, severity=Severity.HIGH),
        SeverityBand(gte=0.2, severity=Severity.MEDIUM),
    ]


def _default_untranslated_bands() -> list[SeverityBand]:
    """漏译：源语言占比 ≥0.9 为 HIGH，阈值～0.9 为 MEDIUM。"""

    return [
        SeverityBand(gte=0.9, severity=Severity.HIGH),
        SeverityBand(gte=0.7, severity=Severity.MEDIUM),
    ]


def _default_resize_bands() -> list[SeverityBand]:
    """尺寸剧变：宽/高变化 ≥80% 为 HIGH，50%～80% 为 MEDIUM。"""

    return [
        SeverityBand(gte=0.8, severity=Severity.HIGH),
        SeverityBand(gte=0.5, severity=Severity.MEDIUM),
    ]


def _default_issue_type_deduction_caps() -> dict[IssueType, float]:
    """返回完整 Issue 类型扣分上限，并作为旧配置升级基线。"""

    return {
        IssueType.REGION_SHIFTED: 12.0,
        IssueType.REGION_RESIZED: 10.0,
        IssueType.TEXT_FRAGMENTED: 10.0,
        IssueType.TEXT_OVERFLOW: 25.0,
        IssueType.TEXT_CLIPPED: 25.0,
        IssueType.ABNORMAL_WRAP: 10.0,
        IssueType.LINE_COUNT_EXPLOSION: 10.0,
        IssueType.FONT_SHRINK: 10.0,
        IssueType.TEXT_OVERLAP: 10.0,
        IssueType.TEXT_IMAGE_OVERLAP: 25.0,
        IssueType.CONTENT_OUT_OF_PAGE: 25.0,
        IssueType.MISSING_ELEMENT: 10.0,
        IssueType.ADDED_ELEMENT: 3.0,
        IssueType.MISSING_IMAGE: 25.0,
        IssueType.TYPOGRAPHY_CHANGED: 10.0,
        IssueType.TABLE_STRUCTURE_CHANGED: 25.0,
        IssueType.PAGE_MISSING: 25.0,
        IssueType.NUMBER_MISMATCH: 12.0,
        IssueType.UNTRANSLATED_TEXT: 12.0,
        IssueType.UNTRANSLATED_RASTER: 12.0,
        IssueType.GLOSSARY_VIOLATION: 12.0,
        IssueType.INVISIBLE_TEXT: 25.0,
        IssueType.TEXT_RASTERIZED: 10.0,
        IssueType.TEXT_VECTORIZED: 0.0,
        IssueType.TEXT_ALIGNMENT_CHANGED: 10.0,
        IssueType.OTHER: 10.0,
    }


class DetectorThresholds(SchemaModel):
    """保存确定性检测器的数值阈值。"""

    shifted_ratio: float = Field(default=0.05, ge=0, le=1)
    severely_shifted_ratio: float = Field(default=0.15, ge=0, le=1)
    font_shrink_ratio: float = Field(default=-0.20, ge=-1, le=0)
    overlap_ratio: float = Field(default=0.05, ge=0, le=1)
    overlap_increase_ratio: float = Field(default=0.05, ge=0, le=1)
    # 文本 BBox 在两个轴向都达到该侵入比例才算真实重叠，排除相邻行/列
    # 因字体上延、下延产生的亚点级边界接触。
    text_overlap_axis_ratio: float = Field(default=0.1, ge=0, le=1)
    image_caption_area_ratio: float = Field(default=0.005, ge=0, le=1)
    # 目标文本区中仍保留源语言文字的字符占比达到该值即判为未翻译。
    untranslated_ratio: float = Field(default=0.7, ge=0, le=1)
    # 漏译判定要求目标文本的最少字母数，短版权行/机构缩写不参与判定。
    untranslated_min_letters: int = Field(default=8, ge=1, le=100)
    # 图像化漏译：多个内容指纹未变化的小图片在译文页聚成大区域时，
    # 视为疑似把源语言字形原样保留。阈值同时限制数量、面积和聚类间距，
    # 避免单张照片、Logo 或零散装饰图被误报。
    untranslated_raster_min_images: int = Field(default=8, ge=2, le=1000)
    untranslated_raster_min_bbox_area_ratio: float = Field(
        default=0.05, ge=0, le=1
    )
    untranslated_raster_min_image_area_ratio: float = Field(
        default=0.01, ge=0, le=1
    )
    untranslated_raster_cluster_x_gap_ratio: float = Field(
        default=0.15, ge=0, le=1
    )
    untranslated_raster_cluster_y_gap_ratio: float = Field(
        default=0.04, ge=0, le=1
    )
    untranslated_raster_position_similarity: float = Field(
        default=0.995, ge=0, le=1
    )
    untranslated_raster_size_similarity: float = Field(
        default=0.995, ge=0, le=1
    )
    # OCR 只处理位置尺寸稳定的大图片；候选、置信度与源语言残留阈值
    # 集中在 Profile，保证同一报告能够复现当时的判定行为。
    untranslated_raster_ocr_min_area_ratio: float = Field(
        default=0.05, ge=0, le=1
    )
    untranslated_raster_ocr_max_candidates: int = Field(
        default=4, ge=1, le=20
    )
    untranslated_raster_ocr_dpi: int = Field(default=216, ge=72, le=600)
    untranslated_raster_ocr_padding_points: float = Field(
        default=1.0, ge=0, le=20
    )
    untranslated_raster_ocr_min_confidence: float = Field(
        default=0.65, ge=0, le=1
    )
    untranslated_raster_ocr_min_source_chars: int = Field(
        default=4, ge=1, le=10000
    )
    untranslated_raster_ocr_min_target_chars: int = Field(
        default=4, ge=1, le=10000
    )
    untranslated_raster_ocr_high_source_chars: int = Field(
        default=30, ge=1, le=10000
    )
    untranslated_raster_ocr_source_ratio: float = Field(
        default=0.15, ge=0, le=1
    )
    # LibreOffice 归一化带来的版面转换噪声容差；偏移类检测阈值自动
    # 叠加该值，纯 PDF 流水线（未归一化）不受影响。
    conversion_noise_ratio: float = Field(default=0.03, ge=0, le=0.2)
    # 严重度分档（幅度 → 严重度）：空列表退回检测器缺省严重度（HIGH）。
    # 指标定义：数字不一致 = 页面差异数字总数；字号缩小 = 缩小幅度（正数）；
    # 漏译 = 目标区域中源脚本字母占比。
    number_mismatch_bands: list[SeverityBand] = Field(
        default_factory=_default_number_bands
    )
    font_shrink_bands: list[SeverityBand] = Field(
        default_factory=_default_font_shrink_bands
    )
    untranslated_bands: list[SeverityBand] = Field(
        default_factory=_default_untranslated_bands
    )
    region_resize_bands: list[SeverityBand] = Field(
        default_factory=_default_resize_bands
    )
    # 尺寸剧变判定的最小幅度（宽/高变化比例的绝对值）；低于该值不判。
    # 归一化转换的常规抖动在 10%～20%，0.5 起步只捕获真实的合并/拆散。
    region_resize_ratio: float = Field(default=0.5, ge=0, le=1)
    # 字号放大判定阈值：放大超过该比例报 TYPOGRAPHY_CHANGED（MEDIUM）。
    font_grow_ratio: float = Field(default=0.25, ge=0, le=2)
    # 文字碎片化判定：Region 宽度（pt）与字母数同时低于上限视为
    # 竖排/拆散碎片（P\nK、SA+E 一类窄列溢出破坏）。
    fragment_max_width: float = Field(default=18.0, gt=0)
    fragment_max_letters: int = Field(default=3, ge=1, le=10)
    # 隐形文字判定：文字颜色与背景色的 RGB 最低通道都达到该值（接近
    # 白色）即视为同色不可见。235/255 ≈ 92% 白，可捕获 #FFFFFF 等
    # 纯白/近白字，同时放过浅灰绿正文（#A7C4B3 最低通道 167）。
    invisible_color_threshold: int = Field(default=235, ge=200, le=255)
    # 文本透明度低于该值视为不可见；透明度由 PDF alpha/255 得到。
    invisible_opacity_threshold: float = Field(default=0.01, ge=0, le=1)
    # 透明目标文本与未匹配图片的重叠达到该比例时，判为局部文字栅格化。
    rasterized_image_overlap_ratio: float = Field(default=0.8, ge=0, le=1)
    # 转曲判定：源页文本字符数达到下限、且目标页文本字符数降到源的
    # 比例以下时，判目标文字已矢量化（转曲），内容级检测（数字/漏译/
    # 术语/文本缺失）在该页抑制并显式提示。
    vectorized_min_source_chars: int = Field(default=30, ge=1, le=10000)
    vectorized_max_target_ratio: float = Field(default=0.1, ge=0, le=1)
    # 对齐检测先把相邻行聚成临时文本流，再根据左右边缘/中心线稳定性
    # 推断 LEFT/RIGHT/CENTER。所有比例均相对页面或行高归一化。
    alignment_min_lines: int = Field(default=3, ge=2, le=20)
    alignment_line_gap_ratio: float = Field(default=0.6, ge=0, le=3)
    alignment_horizontal_overlap_ratio: float = Field(default=0.3, ge=0, le=1)
    alignment_font_size_tolerance_ratio: float = Field(default=0.15, ge=0, le=1)
    alignment_edge_tolerance_ratio: float = Field(default=0.015, ge=0, le=0.2)
    alignment_confidence_margin: float = Field(default=0.01, ge=0, le=0.2)
    alignment_group_match_ratio: float = Field(default=0.6, ge=0, le=1)
    # 短标签的文字墨迹宽度会随语言自然变化；高度和字号稳定时不把
    # 单纯宽度缩短当作 Region 尺寸剧变。
    text_label_max_chars: int = Field(default=30, ge=1, le=200)
    text_resize_height_tolerance_ratio: float = Field(default=0.2, ge=0, le=1)
    text_resize_font_tolerance_ratio: float = Field(default=0.1, ge=0, le=1)
    # 同一文本条目在翻译后自然增加一行时，按每行高度而非整体 BBox 高度
    # 判断尺寸是否稳定，避免正常换行被误判为段落合并。
    text_reflow_max_added_lines: int = Field(default=1, ge=0, le=10)
    text_reflow_width_tolerance_ratio: float = Field(default=0.25, ge=0, le=1)
    text_reflow_font_tolerance_ratio: float = Field(default=0.2, ge=0, le=1)
    text_reflow_line_height_tolerance_ratio: float = Field(default=0.6, ge=0, le=2)

    def band_severity(
        self, bands: list[SeverityBand], value: float, default: Severity
    ) -> Severity:
        """按分档解析严重度：取 gte 不超过指标值的最高档。

        多档命中时取 gte 最大者（幅度越严重档位越高）；全部未命中或
        分档为空时返回 default，保证旧配置（无分档）行为不变。
        """

        hit = max(
            (band for band in bands if value >= band.gte),
            key=lambda band: band.gte,
            default=None,
        )
        return hit.severity if hit else default

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "DetectorThresholds":
        """严重偏移阈值必须大于普通偏移阈值。"""

        if self.severely_shifted_ratio <= self.shifted_ratio:
            raise ValueError("严重偏移阈值必须大于普通偏移阈值")
        return self


class DetectorSettings(SchemaModel):
    """组合检测器开关、阈值与版面类比权重。"""

    enabled: DetectorToggles = Field(default_factory=DetectorToggles)
    thresholds: DetectorThresholds = Field(default_factory=DetectorThresholds)
    # 只覆盖确有业务策略差异的 Issue；未配置项继续使用检测器默认严重度。
    severity_overrides: dict[IssueType, Severity] = Field(
        default_factory=lambda: {IssueType.TEXT_RASTERIZED: Severity.HIGH}
    )
    layout_analog_weights: LayoutAnalogWeights = Field(
        default_factory=LayoutAnalogWeights
    )

    def severity_for(self, issue_type: IssueType, default: Severity) -> Severity:
        """返回规则配置指定的严重度，未覆盖时沿用检测器默认值。"""

        return self.severity_overrides.get(issue_type, default)


class ScoringSettings(SchemaModel):
    """配置严重度扣分、同类上限和最终状态覆盖规则。"""

    pass_score: float = Field(default=90.0, ge=0, le=100)
    fail_score: float = Field(default=75.0, ge=0, le=100)
    critical_forces_fail: bool = True
    high_forces_review: bool = True
    severity_deductions: dict[Severity, float] = Field(
        default_factory=lambda: {
            Severity.INFO: 0.0,
            Severity.LOW: 1.0,
            Severity.MEDIUM: 4.0,
            Severity.HIGH: 10.0,
            Severity.CRITICAL: 25.0,
        }
    )
    issue_type_deduction_caps: dict[IssueType, float] = Field(
        default_factory=_default_issue_type_deduction_caps
    )

    @model_validator(mode="before")
    @classmethod
    def upgrade_issue_type_caps(cls, value: object) -> object:
        """旧配置缺少新增 Issue 类型时补默认上限，保持可重新质检。"""

        if not isinstance(value, dict):
            return value
        existing = value.get("issue_type_deduction_caps")
        if not isinstance(existing, dict):
            return value
        defaults = {
            issue_type.value: cap
            for issue_type, cap in _default_issue_type_deduction_caps().items()
        }
        return {
            **value,
            "issue_type_deduction_caps": {**defaults, **existing},
        }

    @model_validator(mode="after")
    def validate_scores_and_maps(self) -> "ScoringSettings":
        """校验分数线顺序以及所有枚举项均有明确评分配置。"""

        if self.fail_score >= self.pass_score:
            raise ValueError("FAIL 分数线必须低于 PASS 分数线")
        missing_severities = set(Severity) - set(self.severity_deductions)
        if missing_severities:
            raise ValueError(f"缺少严重度扣分配置: {sorted(missing_severities)}")
        missing_issue_types = set(IssueType) - set(self.issue_type_deduction_caps)
        if missing_issue_types:
            raise ValueError(f"缺少问题类型扣分上限: {sorted(missing_issue_types)}")
        if any(value < 0 for value in self.severity_deductions.values()):
            raise ValueError("严重度扣分不能为负数")
        if any(value < 0 for value in self.issue_type_deduction_caps.values()):
            raise ValueError("问题类型扣分上限不能为负数")
        return self


class GroupingSettings(SchemaModel):
    """控制 Block 分组为 Region 时的规则参数。"""

    # 相对页内正文字号显著放大的文本判定为标题的倍数阈值。
    heading_ratio: float = Field(default=1.25, ge=1.0, le=5.0)
    # 同一 PDF 原始 Block 内，两个文本 Span 的水平/垂直间距超过
    # 行高倍数时视为不连通，避免流程图、表格标签被合并成超宽 Region。
    disconnected_span_gap_ratio: float = Field(default=3.0, ge=0.5, le=20.0)
    # 跨行合并时允许的字号浮点误差；绝对值与相对值取较大者。
    style_font_size_tolerance_ratio: float = Field(default=0.03, ge=0, le=0.5)
    style_font_size_tolerance_points: float = Field(default=0.25, ge=0, le=5.0)


class RuleProfile(SchemaModel):
    """一次 QA 任务可复现、可版本化的完整规则配置。"""

    schema_version: int = Field(default=1, ge=1)
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)
    status: ProfileStatus = ProfileStatus.DRAFT
    description: str = ""
    # 翻译场景的脚本对标识（如 "latin-arabic" 表示拉丁源 → 阿拉伯语目标）。
    # "auto" 表示由引擎按文档内容自动推断；不同脚本的排版与数字习惯不同，
    # 可通过 language_overrides 按场景覆盖检测开关与阈值。
    language: str = Field(default="auto", pattern=r"^(auto|[a-z]+(-[a-z]+)?)$")
    language_overrides: dict[str, DetectorSettings] = Field(default_factory=dict)
    matching: MatchingSettings = Field(default_factory=MatchingSettings)
    alignment: PageAlignmentSettings = Field(default_factory=PageAlignmentSettings)
    grouping: GroupingSettings = Field(default_factory=GroupingSettings)
    detectors: DetectorSettings = Field(default_factory=DetectorSettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)

    def detector_settings_for(self, language: str) -> DetectorSettings:
        """返回指定语言场景下生效的检测配置。

        命中 language_overrides 时返回覆盖配置，否则返回全局 detectors；
        阈值判断始终只经由本方法取值，保证阈值来源集中在 RuleProfile。
        """

        return self.language_overrides.get(language, self.detectors)

    @property
    def reference(self) -> str:
        """返回适合报告和界面显示的稳定版本引用。"""

        return f"{self.profile_id}@{self.version}"


def default_rule_profile() -> RuleProfile:
    """返回经过真实中英文 PDF 校准的内置平衡配置。"""

    return RuleProfile(
        profile_id="translation-balanced",
        name="翻译 PDF 平衡模式",
        version=1,
        status=ProfileStatus.PUBLISHED,
        description="适用于机器生成型双语 PDF 的默认平衡配置。",
    )


class RuleProfileStore:
    """负责 Profile JSON 的校验加载和原子保存。"""

    @staticmethod
    def load(path: Path) -> RuleProfile:
        """从 UTF-8 JSON 文件加载并严格校验 Profile。"""

        safe_path = path.expanduser().resolve()
        if not safe_path.is_file() or safe_path.suffix.lower() != ".json":
            raise ValueError(f"无效规则配置文件: {safe_path}")
        return RuleProfile.model_validate_json(safe_path.read_text(encoding="utf-8"))

    @staticmethod
    def save(profile: RuleProfile, path: Path) -> Path:
        """先写临时文件再替换目标，避免界面保存中断产生半份 JSON。"""

        safe_path = path.expanduser().resolve()
        if safe_path.suffix.lower() != ".json":
            raise ValueError("规则配置文件必须使用 .json 扩展名")
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = safe_path.with_suffix(safe_path.suffix + ".tmp")
        temporary_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        temporary_path.replace(safe_path)
        return safe_path

    @staticmethod
    def export_json_schema(path: Path) -> Path:
        """导出 UI 可用于动态表单和客户端校验的 JSON Schema。"""

        safe_path = path.expanduser().resolve()
        if safe_path.suffix.lower() != ".json":
            raise ValueError("JSON Schema 文件必须使用 .json 扩展名")
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = safe_path.with_suffix(safe_path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(
                RuleProfile.model_json_schema(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(safe_path)
        return safe_path
