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
        "--render-scope",
        choices=["all", "issues"],
        default="all",
        help="渲染范围：all 渲染全部页面，issues 只渲染状态非 PASS 的页面",
    )
    parser.add_argument(
        "--verify-stage",
        choices=["parse", "group", "alignment", "match", "detect", "report"],
        default=None,
        help="分阶段验证模式：执行到指定阶段并在终端输出各阶段摘要后退出",
    )
    parser.add_argument(
        "--verify-dir",
        type=Path,
        default=Path("verify-artifacts"),
        help="分阶段验证模式的中间产物输出目录",
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
    parser.add_argument(
        "--export-xlsx",
        type=Path,
        default=None,
        metavar="PATH",
        help="比较完成后额外导出 XLSX 验收问题清单",
    )
    parser.add_argument(
        "--export-html",
        type=Path,
        default=None,
        metavar="PATH",
        help="比较完成后额外导出 HTML 验收报告",
    )
    parser.add_argument(
        "--source-password",
        default=None,
        metavar="PW",
        help="源 PDF 的打开密码（仅 user password 文档需要；权限密码文档无需提供）",
    )
    parser.add_argument(
        "--target-password",
        default=None,
        metavar="PW",
        help="目标 PDF 的打开密码（仅 user password 文档需要）",
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
        if args.verify_stage is not None:
            from document_qa.verify import Stage, StagedVerifier, save_artifacts

            verifier = StagedVerifier(
                DocumentQAPipeline(profile=profile)
            )
            artifacts = verifier.run(
                args.source, args.target, stop_after=Stage(args.verify_stage)
            )
            paths = save_artifacts(artifacts, args.verify_dir)
            for artifact, path in zip(artifacts, paths, strict=True):
                print(f"{artifact.summary}  产物={path}")
            return 0
        report = DocumentQAPipeline(profile=profile).compare(
            args.source,
            args.target,
            render_dir=args.render_dir,
            render_scope=args.render_scope,
            source_password=args.source_password,
            target_password=args.target_password,
        )
        output_path = JSONReporter().write(report, args.output)
        # 可选的验收交付物导出；失败按输入错误处理并保留 JSON 报告。
        exports = []
        if args.export_xlsx is not None:
            from document_qa.reporting.xlsx_reporter import export_xlsx

            exports.append(export_xlsx(report, args.export_xlsx))
        if args.export_html is not None:
            from document_qa.reporting.html_reporter import export_html

            exports.append(export_html(report, args.export_html))
    except (DocumentParsingError, ValueError) as exc:
        print(f"处理失败: {exc}", file=sys.stderr)
        return 2

    print(
        f"状态={report.status.value} 分数={report.document_score:.2f} "
        f"报告={output_path}"
    )
    for path in exports:
        print(f"已导出: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
