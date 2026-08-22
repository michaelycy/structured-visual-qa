"""历史 QAReport 与当前 Schema 的读取兼容测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from document_qa.profiles import default_rule_profile
from document_qa.schemas import IssueType
from document_qa_server.services.history_service import CompareHistoryService


class HistoryCompatibilityTests(unittest.TestCase):
    """验证新增 Profile 字段后旧记录仍可读取和重新质检。"""

    def test_get_upgrades_legacy_profile_snapshot_before_validation(self) -> None:
        """旧快照缺少新 Issue 上限时，读取应补默认值且不改历史结论。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            target = root / "target.pdf"
            source.write_bytes(b"source")
            target.write_bytes(b"target")
            service = CompareHistoryService(artifacts_dir=root)
            report = {
                "source_document_id": "source",
                "target_document_id": "target",
                "rule_profile_reference": "translation-balanced@1",
                "rule_profile_snapshot": default_rule_profile().model_dump(mode="json"),
                "document_score": 100.0,
                "status": "pass",
                "summary": {
                    "pages": 0,
                    "passed_pages": 0,
                    "review_pages": 0,
                    "failed_pages": 0,
                    "issue_counts": {},
                },
                "pages": [],
                "metadata": {},
            }
            record = service.add(
                report=report,
                source_path=str(source),
                target_path=str(target),
                source_display=source.name,
                target_display=target.name,
            )
            legacy_report = json.loads(json.dumps(report))
            del legacy_report["rule_profile_snapshot"]["scoring"][
                "issue_type_deduction_caps"
            ][IssueType.TEXT_RASTERIZED.value]
            with service._database.transaction() as connection:
                connection.execute(
                    "UPDATE comparison_reports SET report_json = ? WHERE record_id = ?",
                    (json.dumps(legacy_report), record.record_id),
                )

            loaded = service.get(record.record_id)

            self.assertEqual(loaded.status, "pass")
            caps = loaded.report["rule_profile_snapshot"]["scoring"][
                "issue_type_deduction_caps"
            ]
            self.assertEqual(caps[IssueType.TEXT_RASTERIZED.value], 10.0)


if __name__ == "__main__":
    unittest.main()
