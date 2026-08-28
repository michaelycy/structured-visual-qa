"""比较隔离执行核心 execute_compare 的单元验证（T23）。

execute_compare 是父进程同步路径与比较子进程共用的执行核心，
本文件只验证函数级行为：报告可产出、渲染索引按任务目录隔离、
关闭渲染时返回空索引。子进程 spawn 与 OCR 链路由真实样例
端到端验证覆盖，不在单元测试中启动。
"""

import tempfile
import unittest
from pathlib import Path

import pymupdf

from document_qa.profiles import default_rule_profile
from document_qa_server.services.compare_worker import execute_compare


def create_pdf(path: Path, *, x_shift: float = 0) -> None:
    """生成无外部资源的测试 PDF，避免仓库保存真实文档样本。"""

    document = pymupdf.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((40 + x_shift, 60), "Structured QA worker", fontsize=14)
    page.insert_textbox(
        pymupdf.Rect(40 + x_shift, 100, 250 + x_shift, 180),
        "Isolated worker execution.",
        fontsize=11,
    )
    document.save(path)
    document.close()


class ExecuteCompareTests(unittest.TestCase):
    """验证父进程与子进程共用的比较执行核心。"""

    def test_returns_report_and_task_scoped_render_index(self) -> None:
        """全量渲染时索引必须落在 pages/task-* 任务子目录内。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            target = root / "target.pdf"
            create_pdf(source)
            create_pdf(target, x_shift=1.0)
            artifacts = root / "artifacts"

            report, rendered = execute_compare(
                artifacts_dir=artifacts,
                source=source,
                target=target,
                profile=default_rule_profile(),
                glossary=None,
                ocr_provider=None,
                render=True,
                render_scope="all",
            )

        self.assertEqual(report.status.value, "pass")
        self.assertEqual(report.summary.pages, 1)
        self.assertTrue(rendered["source"], "全量渲染应产出源页面")
        self.assertTrue(rendered["target"], "全量渲染应产出目标页面")
        for entry in rendered["source"] + rendered["target"]:
            self.assertTrue(
                entry.startswith("task-"),
                "渲染索引必须带任务目录前缀以隔离并发任务",
            )

    def test_render_off_returns_empty_index(self) -> None:
        """render=False 时不创建渲染目录并返回空索引。"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            target = root / "target.pdf"
            create_pdf(source)
            create_pdf(target)
            artifacts = root / "artifacts"

            report, rendered = execute_compare(
                artifacts_dir=artifacts,
                source=source,
                target=target,
                profile=default_rule_profile(),
                glossary=None,
                ocr_provider=None,
                render=False,
            )

            self.assertEqual(report.summary.pages, 1)
            self.assertEqual(rendered, {"source": [], "target": []})
            self.assertFalse((artifacts / "pages").exists())


if __name__ == "__main__":
    unittest.main()
