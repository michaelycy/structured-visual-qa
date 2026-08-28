"""document-qa MCP 服务：把验收工具链以 Model Context Protocol 暴露。

传输为 stdio（本地 MCP 客户端标准形态），直接复用 server 层的
服务实例（CompareService/GlossaryService/ProfileService 等），
不经过 HTTP——MCP 进程是这些服务的库消费者。

面向 LLM 的输出裁剪原则：默认返回摘要（状态/分数/计数/前 N 条问题），
完整报告用 get_report 按需获取并支持页码过滤，避免撑爆上下文。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from document_qa.profiles import default_rule_profile
from document_qa_server.persistence import Database
from document_qa_server.services import (
    CompareService,
    FileService,
    GlossaryService,
    NormalizationService,
    ProfileService,
)
from document_qa_server.services.history_service import CompareHistoryService
from document_qa_server.settings import load_settings

mcp = FastMCP("document-qa")

# 服务实例在模块级创建一次（MCP 进程通常单客户端，无并发竞争问题）。
_SETTINGS = load_settings()
_ROOT = _SETTINGS.artifacts_dir
_ROOT.mkdir(parents=True, exist_ok=True)
_DATABASE = Database(artifacts_dir=_ROOT)
_COMPARE = CompareService(artifacts_dir=_ROOT)
_HISTORY = CompareHistoryService(artifacts_dir=_ROOT, database=_DATABASE)
_PROFILES = ProfileService(artifacts_dir=_ROOT, database=_DATABASE)
_GLOSSARIES = GlossaryService(artifacts_dir=_ROOT, database=_DATABASE)
_FILES = FileService(
    artifacts_dir=_ROOT,
    samples_dir=_SETTINGS.samples_dir,
    max_upload_bytes=_SETTINGS.max_upload_bytes,
)
_NORMALIZER = NormalizationService(artifacts_dir=_ROOT)

# MCP 场景同步执行更合适：客户端（LLM）本身就是逐工具调用并等待，
# BackgroundTasks 的异步语义反而让对话轮次复杂化。
_SYNC_LOCK = threading.Lock()


def _summary(report: dict, issue_limit: int = 10) -> dict:
    """把完整报告裁剪成 LLM 友好的摘要。"""

    issues = [
        {
            "page": issue["page"],
            "type": issue["type"],
            "severity": issue["severity"],
            "description": issue["description"],
        }
        for page in report.get("pages", [])
        for issue in page.get("issues", [])
    ]
    return {
        "status": report.get("status"),
        "document_score": report.get("document_score"),
        "pages": report.get("summary", {}).get("pages"),
        "issue_counts": report.get("summary", {}).get("issue_counts"),
        "rule_profile_reference": report.get("rule_profile_reference"),
        "normalized_from": (report.get("metadata") or {}).get("normalized_from"),
        "top_issues": issues[:issue_limit],
        "total_issues": len(issues),
    }


@mcp.tool()
def compare_documents(
    source: str,
    target: str,
    glossary_reference: str | None = None,
    profile_path: str | None = None,
) -> str:
    """比较源文档与目标文档（PDF 或 Office 格式），返回报告摘要。

    Args:
        source: 源文档（原文）的本地绝对路径
        target: 目标文档（译文）的本地绝对路径
        glossary_reference: 可选术语库引用（格式 id@version，如 un-core@1）
        profile_path: 可选规则配置 JSON 的本地路径
    """
    source_path = Path(source).expanduser().resolve()
    target_path = Path(target).expanduser().resolve()
    if not source_path.is_file() or not target_path.is_file():
        return json.dumps({"error": f"文件不存在: {source} / {target}"}, ensure_ascii=False)
    profile = default_rule_profile()
    if profile_path:
        try:
            profile = _PROFILES.load(Path(profile_path))
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
    glossary = None
    if glossary_reference:
        try:
            glossary = _GLOSSARIES.load_by_reference(glossary_reference)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
    try:
        with _SYNC_LOCK:
            report, _rendered = _COMPARE.run(
                source_path, target_path, profile=profile, glossary=glossary, render=False
            )
    except Exception as exc:
        return json.dumps({"error": f"比较失败: {exc}"}, ensure_ascii=False)
    # 同步执行但复用历史记录，保持与 Web 界面一致的可回查性。
    record = _HISTORY.add(
        report=report.model_dump(mode="json"),
        source_path=str(source_path),
        target_path=str(target_path),
        source_display=source_path.name,
        target_display=target_path.name,
    )
    result = _summary(report.model_dump(mode="json"))
    result["history_record_id"] = record.record_id
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_history() -> str:
    """列出历史比较记录（时间倒序的摘要列表）。"""

    records = _HISTORY.list()
    return json.dumps(
        {
            "records": [
                {
                    "record_id": r.record_id,
                    "created_at": r.created_at,
                    "source_display": r.source_display,
                    "target_display": r.target_display,
                    "status": r.status,
                    "document_score": r.document_score,
                    "issue_total": r.issue_total,
                    "problem_total": r.problem_total,
                }
                for r in records[:30]
            ]
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_report(record_id: str, page: int | None = None) -> str:
    """读取历史记录的完整报告；page 参数只取单页明细。

    Args:
        record_id: 历史记录 ID（list_history 获得）
        page: 可选页码；缺省返回文档级摘要 + 全部问题列表
    """
    try:
        record = _HISTORY.get(record_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    report = record.report
    if page is not None:
        page_data = next(
            (p for p in report.get("pages", []) if p["page"] == page), None
        )
        return json.dumps(
            {"page": page_data or f"第 {page} 页不存在"}, ensure_ascii=False, indent=2
        )
    return json.dumps(_summary(report, issue_limit=10**6), ensure_ascii=False, indent=2)


@mcp.tool()
def export_report(record_id: str, format: str = "xlsx", output_dir: str = ".") -> str:
    """把历史记录导出为 XLSX 或 HTML 验收交付物，返回文件路径。

    Args:
        record_id: 历史记录 ID
        format: xlsx 或 html
        output_dir: 输出目录（本地路径）
    """
    from document_qa.reporting.html_reporter import export_html
    from document_qa.reporting.xlsx_reporter import export_xlsx
    from document_qa.schemas import QAReport

    try:
        record = _HISTORY.get(record_id)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    if not record.report:
        return json.dumps({"error": "该记录不含完整报告"}, ensure_ascii=False)
    if format not in ("xlsx", "html"):
        return json.dumps({"error": "format 只支持 xlsx 或 html"}, ensure_ascii=False)
    report = QAReport.model_validate(record.report)
    out = Path(output_dir).expanduser().resolve()
    if format == "xlsx":
        path = export_xlsx(report, out / f"{record_id}.xlsx")
    else:
        path = export_html(report, out / f"{record_id}.html")
    return json.dumps({"exported": str(path)}, ensure_ascii=False)


@mcp.tool()
def verify_stage(source: str, target: str, stop_after: str = "report") -> str:
    """分阶段执行验证流水线（调试与教学用），返回各阶段摘要。

    Args:
        source: 源文档本地路径
        target: 目标文档本地路径
        stop_after: parse/group/alignment/match/detect/report
    """
    from document_qa.verify import Stage, StagedVerifier

    try:
        stop = Stage(stop_after)
    except ValueError:
        return json.dumps({"error": f"未知阶段: {stop_after}"}, ensure_ascii=False)
    artifacts = StagedVerifier().run(
        Path(source).expanduser().resolve(),
        Path(target).expanduser().resolve(),
        stop_after=stop,
    )
    return json.dumps(
        {"stages": [{"stage": a.stage.value, "summary": a.summary} for a in artifacts]},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def list_profiles() -> str:
    """列出已保存的规则配置（Profile）摘要。"""

    items = _PROFILES.list()
    return json.dumps(
        {
            "profiles": [
                {
                    "filename": i.filename,
                    "name": i.name,
                    "reference": i.reference,
                    "status": i.status,
                }
                for i in items
            ]
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_profile(filename: str) -> str:
    """读取已保存规则配置的完整内容。"""

    try:
        profile = _PROFILES.get(filename)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return profile.model_dump_json(indent=2)


@mcp.tool()
def save_profile(profile_json: str) -> str:
    """校验并保存规则配置（传入完整 Profile JSON 文本）。"""

    try:
        path, reference = _PROFILES.save(json.loads(profile_json))
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps({"saved": str(path), "reference": reference}, ensure_ascii=False)


@mcp.tool()
def list_glossaries() -> str:
    """列出已保存的术语库摘要。"""

    items = _GLOSSARIES.list()
    return json.dumps(
        {
            "glossaries": [
                {
                    "filename": i.filename,
                    "name": i.name,
                    "reference": i.reference,
                    "entry_count": i.entry_count,
                }
                for i in items
            ]
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def get_glossary(filename: str) -> str:
    """读取术语库完整内容。"""

    try:
        glossary = _GLOSSARIES.get(filename)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return glossary.model_dump_json(indent=2)


@mcp.tool()
def save_glossary(glossary_json: str) -> str:
    """校验并保存术语库（传入完整 Glossary JSON 文本）。"""

    try:
        path, reference = _GLOSSARIES.save(json.loads(glossary_json))
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps({"saved": str(path), "reference": reference}, ensure_ascii=False)


@mcp.tool()
def engine_status() -> str:
    """探测引擎能力：归一化引擎（LibreOffice）与支持格式。"""

    version = NormalizationService.check_engine()
    return json.dumps(
        {
            "normalize_engine_available": version is not None,
            "normalize_engine_version": version,
            "supported_office_formats": NormalizationService.supported_extensions(),
        },
        ensure_ascii=False,
    )


def main() -> None:
    """stdio 模式入口（pyproject [project.scripts] 指向这里）。"""

    mcp.run()


if __name__ == "__main__":
    main()
