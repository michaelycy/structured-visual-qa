import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from document_qa.profiles import (
    DetectorToggles,
    MatchingWeights,
    RuleProfile,
    RuleProfileStore,
    default_rule_profile,
)
from document_qa.schemas import (
    BoundingBox,
    ElementType,
    IssueType,
    Page,
    Region,
    Severity,
)
from document_qa.detectors import RuleDetector
from document_qa.matching import RegionMatcher


class RuleProfileTests(unittest.TestCase):
    """验证 Profile 校验、持久化和运行时生效行为。"""

    def test_rejects_matching_weights_not_equal_to_one(self) -> None:
        """界面提交的匹配权重总和不是 1 时必须拒绝。"""

        with self.assertRaisesRegex(ValidationError, "权重总和必须等于 1"):
            MatchingWeights(position=0.5, size=0.5, type=0.5, order=0)

    def test_rejects_invalid_threshold_order(self) -> None:
        """严重偏移阈值不能小于或等于普通偏移阈值。"""

        payload = default_rule_profile().model_dump(mode="json")
        payload["detectors"]["thresholds"]["shifted_ratio"] = 0.2
        payload["detectors"]["thresholds"]["severely_shifted_ratio"] = 0.1

        with self.assertRaisesRegex(ValidationError, "严重偏移阈值"):
            RuleProfile.model_validate(payload)

    def test_store_round_trip_preserves_profile_version(self) -> None:
        """Profile 保存再加载后，版本引用和内容必须完全一致。"""

        profile = default_rule_profile()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            RuleProfileStore.save(profile, path)

            loaded = RuleProfileStore.load(path)

        self.assertEqual(loaded, profile)
        self.assertEqual(loaded.reference, "translation-balanced@1")

    def test_exports_json_schema_for_ui_form(self) -> None:
        """导出的 JSON Schema 应包含 Profile 顶层字段和嵌套定义。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rule-profile.schema.json"
            RuleProfileStore.export_json_schema(path)

            payload = path.read_text(encoding="utf-8")

        self.assertIn('"profile_id"', payload)
        self.assertIn('"MatchingWeights"', payload)

    def test_detector_toggle_changes_runtime_result(self) -> None:
        """关闭偏移检测器后，同一匹配结果不再产生偏移 Issue。"""

        source = Page(
            document_id="source",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="source-region",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=10, y=10, width=100, height=20),
                )
            ],
        )
        target = Page(
            document_id="target",
            page=1,
            width=200,
            height=200,
            regions=[
                Region(
                    id="target-region",
                    page=1,
                    type=ElementType.PARAGRAPH,
                    bbox=BoundingBox(x=50, y=10, width=100, height=20),
                )
            ],
        )
        base = default_rule_profile()
        profile = base.model_copy(
            update={
                "detectors": base.detectors.model_copy(
                    update={
                        "enabled": DetectorToggles(region_shifted=False)
                    }
                )
            }
        )
        result = RegionMatcher(profile).match_page(source, target)

        issues = RuleDetector(profile).detect(source, target, result)

        self.assertEqual(issues, [])

    def test_rasterized_severity_override_defaults_to_high(self) -> None:
        """文本改为图片显示默认保持 HIGH，并允许规则配置覆盖为提示。"""

        settings = default_rule_profile().detectors

        self.assertEqual(
            settings.severity_for(IssueType.TEXT_RASTERIZED, Severity.HIGH),
            Severity.HIGH,
        )
        configured = settings.model_copy(
            update={
                "severity_overrides": {
                    IssueType.TEXT_RASTERIZED: Severity.INFO,
                }
            }
        )
        self.assertEqual(
            configured.severity_for(IssueType.TEXT_RASTERIZED, Severity.HIGH),
            Severity.INFO,
        )


if __name__ == "__main__":
    unittest.main()
