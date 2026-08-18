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


class MatchingSettings(SchemaModel):
    """控制 Region 候选匹配和文本合并容错。"""

    minimum_score: float = Field(default=0.45, ge=0, le=1)
    merged_text_coverage_ratio: float = Field(default=0.40, ge=0, le=1)
    weights: MatchingWeights = Field(default_factory=MatchingWeights)


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


class DetectorThresholds(SchemaModel):
    """保存确定性检测器的数值阈值。"""

    shifted_ratio: float = Field(default=0.05, ge=0, le=1)
    severely_shifted_ratio: float = Field(default=0.15, ge=0, le=1)
    font_shrink_ratio: float = Field(default=-0.20, ge=-1, le=0)
    overlap_ratio: float = Field(default=0.05, ge=0, le=1)
    overlap_increase_ratio: float = Field(default=0.05, ge=0, le=1)
    image_caption_area_ratio: float = Field(default=0.005, ge=0, le=1)
    # 目标文本区中仍保留源语言文字的字符占比达到该值即判为未翻译。
    untranslated_ratio: float = Field(default=0.7, ge=0, le=1)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "DetectorThresholds":
        """严重偏移阈值必须大于普通偏移阈值。"""

        if self.severely_shifted_ratio <= self.shifted_ratio:
            raise ValueError("严重偏移阈值必须大于普通偏移阈值")
        return self


class DetectorSettings(SchemaModel):
    """组合检测器开关与阈值。"""

    enabled: DetectorToggles = Field(default_factory=DetectorToggles)
    thresholds: DetectorThresholds = Field(default_factory=DetectorThresholds)


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
        default_factory=lambda: {
            IssueType.REGION_SHIFTED: 12.0,
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
            IssueType.OTHER: 10.0,
        }
    )

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


class RuleProfile(SchemaModel):
    """一次 QA 任务可复现、可版本化的完整规则配置。"""

    schema_version: int = Field(default=1, ge=1)
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    version: int = Field(default=1, ge=1)
    status: ProfileStatus = ProfileStatus.DRAFT
    description: str = ""
    matching: MatchingSettings = Field(default_factory=MatchingSettings)
    alignment: PageAlignmentSettings = Field(default_factory=PageAlignmentSettings)
    detectors: DetectorSettings = Field(default_factory=DetectorSettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)

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
