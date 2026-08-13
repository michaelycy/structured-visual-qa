"""Structured Visual QA 命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from document_qa.parsers import DocumentParsingError
from document_qa.pipeline import DocumentQAPipeline
from document_qa.reporting import JSONReporter


def build_parser() -> argparse.ArgumentParser:
    """构造独立函数，便于测试命令行参数而不启动流水线。"""

    parser = argparse.ArgumentParser(
        prog="document-qa",
        description="比较源 PDF 与翻译后 PDF 的结构和视觉保真度。",
    )
    parser.add_argument("source", type=Path, help="源 PDF 路径")
    parser.add_argument("target", type=Path, help="目标 PDF 路径")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("qa-report.json"),
        help="JSON 报告输出路径，默认 qa-report.json",
    )
    parser.add_argument(
        "--render-dir",
        type=Path,
        default=None,
        help="可选页面 PNG 输出目录",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行比较任务；预期输入错误返回 2，避免向终端输出内部堆栈。"""

    args = build_parser().parse_args(argv)
    try:
        report = DocumentQAPipeline().compare(
            args.source, args.target, render_dir=args.render_dir
        )
        output_path = JSONReporter().write(report, args.output)
    except (DocumentParsingError, ValueError) as exc:
        print(f"处理失败: {exc}", file=sys.stderr)
        return 2

    print(
        f"状态={report.status.value} 分数={report.document_score:.2f} "
        f"报告={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

