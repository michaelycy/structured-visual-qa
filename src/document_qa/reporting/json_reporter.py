"""将 QAReport 安全写入 UTF-8 JSON。"""

from pathlib import Path

from document_qa.schemas import QAReport


class JSONReporter:
    """负责报告序列化，不修改任何检测和评分结果。"""

    def write(self, report: QAReport, output_path: Path) -> Path:
        """先写临时文件再原子替换，避免中断留下半份报告。"""

        safe_path = output_path.expanduser().resolve()
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = safe_path.with_suffix(safe_path.suffix + ".tmp")
        temporary_path.write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        temporary_path.replace(safe_path)
        return safe_path

