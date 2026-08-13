"""将 QAReport 安全写入 UTF-8 JSON。"""

from pathlib import Path

from document_qa.schemas import QAReport


class JSONReporter:
    """负责报告序列化，不修改任何检测和评分结果。"""

    def write(self, report: QAReport, output_path: Path) -> Path:
        """创建父目录并写入格式化 JSON，返回最终绝对路径。"""

        safe_path = output_path.expanduser().resolve()
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        return safe_path

