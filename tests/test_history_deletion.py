"""对比记录删除（单条/批量）与衍生渲染目录回收测试。"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from document_qa.profiles import default_rule_profile
from document_qa_server.api.app import create_app
from document_qa_server.services.history_service import CompareHistoryService
from document_qa_server.settings import ServerSettings


def _sample_report() -> dict:
    """构造可通过 QAReport 校验的最小报告。"""

    return {
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


def _make_render_dir(root: Path, task_name: str) -> Path:
    """构造一个渲染任务目录，模拟 compare 产出的页面 PNG。"""

    task_dir = root / "pages" / task_name / "source"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "page-0001.png").write_bytes(b"png")
    return task_dir.parent


def _make_service(root: Path) -> CompareHistoryService:
    """在临时目录构造历史服务与可用的输入文档。"""

    source = root / "source.pdf"
    target = root / "target.pdf"
    source.write_bytes(b"source")
    target.write_bytes(b"target")
    return CompareHistoryService(artifacts_dir=root)


class HistoryDeletionTests(unittest.TestCase):
    """验证记录删除的事务边界、级联与衍生文件回收。"""

    def test_delete_single_removes_report_and_orphan_render_dir(self) -> None:
        """单条删除应级联删除报告，并回收该记录独占的渲染目录。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = _make_service(root)
            render_dir = _make_render_dir(root, "task-aaaaaaaaaa")
            record = service.add(
                report=_sample_report(),
                source_path=str(root / "source.pdf"),
                target_path=str(root / "target.pdf"),
                source_display="source.pdf",
                target_display="target.pdf",
                rendered={"source": ["task-aaaaaaaaaa/source/page-0001.png"]},
            )

            self.assertTrue(service.delete(record.record_id))
            self.assertFalse((root / "pages" / "task-aaaaaaaaaa").exists())
            self.assertFalse(render_dir.exists())
            with self.assertRaises(ValueError):
                service.get(record.record_id)
            with service._database.transaction() as connection:
                remaining = connection.execute(
                    "SELECT count(*) AS n FROM comparison_reports WHERE record_id = ?",
                    (record.record_id,),
                ).fetchone()
            self.assertEqual(remaining["n"], 0)

    def test_shared_render_dir_survives_until_last_reference_gone(self) -> None:
        """共享渲染目录须保留到最后一条引用记录删除为止。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = _make_service(root)
            _make_render_dir(root, "task-sharedabc")
            first = service.add(
                report=_sample_report(),
                source_path=str(root / "source.pdf"),
                target_path=str(root / "target.pdf"),
                source_display="source.pdf",
                target_display="target.pdf",
                rendered={"source": ["task-sharedabc/source/page-0001.png"]},
            )
            second = service.add(
                report=_sample_report(),
                source_path=str(root / "source.pdf"),
                target_path=str(root / "target.pdf"),
                source_display="source.pdf",
                target_display="target.pdf",
                rendered={"source": ["task-sharedabc/source/page-0001.png"]},
            )

            self.assertTrue(service.delete(first.record_id))
            self.assertTrue((root / "pages" / "task-sharedabc").exists())
            self.assertTrue(service.delete(second.record_id))
            self.assertFalse((root / "pages" / "task-sharedabc").exists())

    def test_delete_many_reports_missing_and_invalid_ids(self) -> None:
        """批量删除对不存在与非法 ID 不报错，归入 missing 回告调用方。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = _make_service(root)
            record = service.add(
                report=_sample_report(),
                source_path=str(root / "source.pdf"),
                target_path=str(root / "target.pdf"),
                source_display="source.pdf",
                target_display="target.pdf",
            )

            result = service.delete_many([record.record_id, "20260101-000000-000-x", "坏ID"])

            self.assertEqual(result["deleted"], [record.record_id])
            self.assertEqual(result["missing"], ["20260101-000000-000-x", "坏ID"])
            self.assertEqual(service.list(), [])


class HistoryDeleteApiTests(unittest.TestCase):
    """验证删除路由的状态码与响应契约。"""

    def test_delete_route_and_batch_route(self) -> None:
        """DELETE 命中 200、重复 404；批量路由分别回告 deleted 与 missing。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = _make_service(root)
            record = service.add(
                report=_sample_report(),
                source_path=str(root / "source.pdf"),
                target_path=str(root / "target.pdf"),
                source_display="source.pdf",
                target_display="target.pdf",
            )
            settings = ServerSettings(
                artifacts_dir=root,
                samples_dir=Path(__file__).resolve().parents[1] / "examples",
                log_file_enabled=False,
                ocr_enabled=False,
            )
            client = TestClient(create_app(settings=settings))

            response = client.delete(f"/api/history/item/{record.record_id}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["deleted"], [record.record_id])

            repeated = client.delete(f"/api/history/item/{record.record_id}")
            self.assertEqual(repeated.status_code, 404)

            batch = client.post(
                "/api/history/delete-batch",
                json={"record_ids": ["20260101-000000-000-x"]},
            )
            self.assertEqual(batch.status_code, 200)
            self.assertEqual(batch.json()["missing"], ["20260101-000000-000-x"])

            invalid = client.post("/api/history/delete-batch", json={"record_ids": []})
            self.assertEqual(invalid.status_code, 422)


if __name__ == "__main__":
    unittest.main()
