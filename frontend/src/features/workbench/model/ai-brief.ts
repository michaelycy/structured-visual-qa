/** AI 排查任务书生成（开发者模式）：纯函数，不触碰网络与全局状态。
 *
 * 任务书面向 DSH 等 AI 代理：携带 issue 证据、环境锚点与本项目强制的
 * 开发契约约定，粘贴到 AI 对话即可开工。检测器诊断映射镜像自
 * server/src/document_qa_server/services/review_insight_service.py 的
 * _DETECTOR_DIAGNOSTICS（彼处供误报归因，此处供任务书），两处必须同步维护。
 */

import type { Issue, QAReport } from "../../../api"
import { ISSUE_TYPE_META, SEVERITY_META } from "../../../uiTokens"

// ---- 开发者模式持久化（localStorage；非可分享状态，不进 URL） ----------

const DEV_MODE_STORAGE_KEY = "qa.devMode"

export function isDevModeEnabled(): boolean {
  try {
    return window.localStorage.getItem(DEV_MODE_STORAGE_KEY) === "1"
  } catch {
    return false
  }
}

export function setDevModeEnabled(value: boolean): void {
  try {
    if (value) window.localStorage.setItem(DEV_MODE_STORAGE_KEY, "1")
    else window.localStorage.removeItem(DEV_MODE_STORAGE_KEY)
  } catch {
    // 隐私模式等场景写入失败：仅影响记忆开关，不阻塞功能。
  }
}

// ---- 检测器 → 疑似阶段与代码检索起点（镜像服务端映射，保持同步） --------

interface DetectorDiagnostic {
  stage: string
  locations: string[]
}

const DETECTOR_DIAGNOSTICS: Record<string, DetectorDiagnostic> = {
  "content-numbers": { stage: "detect", locations: ["core/src/document_qa/detectors/content.py"] },
  "content-untranslated": { stage: "detect", locations: ["core/src/document_qa/detectors/content.py"] },
  glossary: { stage: "detect", locations: ["core/src/document_qa/detectors/glossary.py"] },
  "page-alignment": { stage: "alignment", locations: ["core/src/document_qa/matching/page_aligner.py", "core/src/document_qa/pipeline.py"] },
  geometry: { stage: "detect", locations: ["core/src/document_qa/detectors/rules.py", "core/src/document_qa/matching/region_matcher.py"] },
  "missing-element": { stage: "match", locations: ["core/src/document_qa/matching/region_matcher.py", "core/src/document_qa/detectors/rules.py"] },
  typography: { stage: "detect", locations: ["core/src/document_qa/detectors/rules.py"] },
  fragmentation: { stage: "group", locations: ["core/src/document_qa/grouping", "core/src/document_qa/detectors/rules.py"] },
  "text-alignment": { stage: "detect", locations: ["core/src/document_qa/detectors/alignment.py"] },
  overlap: { stage: "detect", locations: ["core/src/document_qa/detectors/rules.py"] },
  overflow: { stage: "detect", locations: ["core/src/document_qa/detectors/rules.py"] },
  "text-rasterization": { stage: "parse", locations: ["core/src/document_qa/parsers/pymupdf_parser.py", "core/src/document_qa/detectors/rules.py"] },
  pipeline: { stage: "detect", locations: ["core/src/document_qa/pipeline.py"] },
}

const FALLBACK_DIAGNOSTIC: DetectorDiagnostic = {
  stage: "detect",
  locations: ["core/src/document_qa/detectors", "core/src/document_qa/pipeline.py"],
}

// ---- 任务书组装 ---------------------------------------------------------

/** 参与任务书的一条 issue 及其全报告连续编号（与列表展示编号一致）。 */
export interface BriefIssue {
  issue: Issue
  number: number
}

export interface IssueBriefInput {
  report: QAReport
  issues: BriefIssue[]
  /** 历史记录 ID；为空时任务书标注"以当前报告数据为准"。 */
  historyRecordId: string | null
  sourceDisplay: string
  targetDisplay: string
  /** 用户追加描述原文；可为空。 */
  note: string
}

const WORK_CONVENTIONS = `## 工作约定（强制，逐条遵守）

- 以 docs/project-contract.md 与 AGENTS.md 为基线：契约优先；认为契约本身有问题时，先提出修改建议并等用户确认，不得绕过。
- 先复现诊断（document-qa --verify-stage 分阶段 / tests/ 定向用例），确认根因后再动手；不得以降级严重度、放宽阈值或跳过测试掩盖问题。
- 遵守分层边界：core 零 HTTP、禁止 import server/persistence；api → services → core；frontend 组件禁止直接 fetch，请求必须走 services 层与 TanStack Query。
- 检测阈值与权重只能写入 core/src/document_qa/profiles.py 的 RuleProfile；触碰契约 §12（删除/重命名公开字段、匹配权重、严重度阈值、更换 PDF 引擎）必须先说明影响并等待用户确认。
- 代码设计与拆分要求：单一职责、模块边界清晰，新增能力先进 core 或对应 feature；公共类/函数写中文 Docstring，主要逻辑用中文注释解释设计目的；标识符与公开 JSON 字段用英文；禁止无关重构与全局格式化；不做与当前任务无关的文件迁移。
- 完成后按契约 §11 验收：uv lock --check、ruff check、渐进 mypy、python -m compileall、双包构建通过；涉及解析/分组/对齐/匹配/检测/评分/报告行为时，用 examples/ 真实 PDF 对逐阶段验证并展示摘要；逐条说明修改点的行为不变式。`

function issueSection(item: BriefIssue): string {
  const { issue, number } = item
  const typeLabel = ISSUE_TYPE_META[issue.type] ?? issue.type
  const severityLabel = SEVERITY_META[issue.severity]?.label ?? issue.severity
  const bbox = issue.bbox
    ? `x=${issue.bbox.x}, y=${issue.bbox.y}, width=${issue.bbox.width}, height=${issue.bbox.height}`
    : "无（页面级问题）"
  return [
    `### #${number} ${typeLabel}（${issue.type}）`,
    `- 位置：第 ${issue.page} 页 · 严重度：${severityLabel}（${issue.severity}） · 检测器：${issue.detector ?? "unknown"} · Issue ID：${issue.id}`,
    `- 描述：${issue.description}`,
    `- bbox：${bbox}`,
    "- metrics（阈值判断依据与原文/译文证据，完整 JSON）：",
    "```json",
    JSON.stringify(issue.metrics ?? {}, null, 2),
    "```",
  ].join("\n")
}

/** 组装 AI 排查任务书 Markdown；纯函数，输出仅由输入决定。 */
export function buildIssueBrief(input: IssueBriefInput): string {
  const { report, issues, historyRecordId, sourceDisplay, targetDisplay, note } = input
  const diagnostics = new Map<string, DetectorDiagnostic>()
  for (const { issue } of issues) {
    const detector = issue.detector ?? "unknown"
    if (!diagnostics.has(detector)) {
      diagnostics.set(detector, DETECTOR_DIAGNOSTICS[detector] ?? FALLBACK_DIAGNOSTIC)
    }
  }

  const lines: string[] = [
    "# AI 排查任务书（Structured Visual QA 工作台开发者模式生成）",
    "",
    "## 任务",
    "",
    "针对下列 issue 完成根因排查：确认代码缺陷后按最佳实践修复；确认检测逻辑正确则给出误报原因与证据。禁止以降级严重度、放宽阈值或跳过测试掩盖问题。",
    "",
    "用户追加描述：",
    "",
    note.trim() || "（用户未追加描述）",
    "",
    "## 环境锚点",
    "",
    historyRecordId
      ? `- 历史记录：${historyRecordId}；完整报告：GET /api/history/item/${historyRecordId}（服务 http://127.0.0.1:8765）`
      : "- 历史记录：无（以本任务书内嵌数据为准）",
    `- 文档对：${sourceDisplay || "（未知）"} → ${targetDisplay || "（未知）"}`,
    `- 报告：状态 ${report.status} · 分数 ${report.document_score} · 规则配置 ${report.rule_profile_reference} · 共 ${report.summary.pages} 页`,
    "",
    `## Issue 明细（共 ${issues.length} 条）`,
    "",
    ...issues.flatMap((item) => [issueSection(item), ""]),
    "## 疑似阶段与代码检索起点（仅是导航线索，必须复现确认根因）",
    "",
    ...[...diagnostics.entries()].map(
      ([detector, diagnostic]) =>
        `- ${detector}：${diagnostic.stage} 阶段，起点 ${diagnostic.locations.join("、")}`,
    ),
    "",
    WORK_CONVENTIONS,
    "",
  ]
  return lines.join("\n")
}
