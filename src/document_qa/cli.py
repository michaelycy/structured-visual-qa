"""Structured Visual QA 命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from document_qa.parsers import DocumentParsingError
from document_qa.pipeline import DocumentQAPipeline
from document_qa.profiles import RuleProfileStore, default_rule_profile
from document_qa.reporting import JSONReporter


def build_parser() -> argparse.ArgumentParser:
    """构造独立函数，便于测试命令行参数而不启动流水线。"""

    parser = argparse.ArgumentParser(
        prog="document-qa",
        description="比较源 PDF 与翻译后 PDF 的结构和视觉保真度。",
    )
    parser.add_argument("source", type=Path, nargs="?", help="源 PDF 路径")
    parser.add_argument("target", type=Path, nargs="?", help="目标 PDF 路径")
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
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="可选 Rule Profile JSON 路径；缺省使用内置平衡配置",
    )
    parser.add_argument(
        "--export-default-profile",
        type=Path,
        default=None,
        metavar="PATH",
        help="导出内置规则配置到 JSON 后退出",
    )
    parser.add_argument(
        "--export-profile-schema",
        type=Path,
        default=None,
        metavar="PATH",
        help="导出 Rule Profile JSON Schema 后退出，供配置界面生成表单",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行比较任务；预期输入错误返回 2，避免向终端输出内部堆栈。"""

    args = build_parser().parse_args(argv)
    try:
        if args.export_default_profile is not None:
            output_path = RuleProfileStore.save(
                default_rule_profile(), args.export_default_profile
            )
            print(f"已导出默认规则配置: {output_path}")
            return 0
        if args.export_profile_schema is not None:
            output_path = RuleProfileStore.export_json_schema(
                args.export_profile_schema
            )
            print(f"已导出规则配置 JSON Schema: {output_path}")
            return 0
        if args.source is None or args.target is None:
            raise ValueError("比较任务必须同时提供源 PDF 和目标 PDF")
        profile = (
            RuleProfileStore.load(args.profile)
            if args.profile is not None
            else default_rule_profile()
        )
        report = DocumentQAPipeline(profile=profile).compare(
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
