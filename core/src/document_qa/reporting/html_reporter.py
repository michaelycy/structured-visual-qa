"""验收报告导出为单文件 HTML。

内联 CSS、无外部依赖，可直接邮件发送或在浏览器打开；需复核页面的
渲染 PNG 以相对路径引用（与 pages/ 渲染产物同目录分发时可见）。
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from document_qa.schemas import QAReport

_ENV = Environment(
    loader=PackageLoader("document_qa.reporting", "templates/"),
    autoescape=select_autoescape(["html"]),
)


def export_html(report: QAReport, output_path: Path) -> Path:
    """把 QA 报告渲染成 HTML 验收单，返回最终路径。"""

    template = _ENV.get_template("report.html.j2")
    pages = [
        {
            "page": page.page,
            "score": round(page.score, 1),
            "status": page.status.value,
            "issues": [
                {
                    "type": issue.type.value,
                    "severity": issue.severity.value,
                    "description": issue.description,
                }
                for issue in page.issues
            ],
        }
        for page in report.pages
        if page.status != "pass" or page.issues
    ]
    html = template.render(
        report=report,
        summary=report.summary,
        pages=pages,
        normalized_from=report.metadata.get("normalized_from"),
    )
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
