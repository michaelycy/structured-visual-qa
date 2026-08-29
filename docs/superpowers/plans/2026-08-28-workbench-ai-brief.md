# 工作台开发者模式：AI 排查任务书 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在工作台规则命中列表提供开发者模式：选中单条或多条 issue、追加描述，一键生成符合项目契约的 AI 排查任务书并复制到剪贴板。

**架构：** 纯前端实现，零后端改动。任务书由纯函数模块组装 Markdown；devMode 为 PageDetails 本地状态持久化到 localStorage；诊断映射镜像 server 端 `_DETECTOR_DIAGNOSTICS`。文档对显示名通过 props 从路由页传入（工作台用当前选择、历史抽屉用记录本身），避免 useContext 读到错误配对。

**技术栈：** React 19 + TypeScript + antd v6 + TanStack（无新增依赖）。前端无单元测试框架（规格约定不引入），自动化门禁为 `bun run build`（tsc + vite）与 `bun run lint`（oxlint），辅以手工验收清单。

**规格：** `docs/superpowers/specs/2026-08-28-workbench-ai-brief-design.md`

---

## 文件结构

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `frontend/src/features/workbench/model/ai-brief.ts` | 创建 | 纯函数：devMode 持久化、诊断映射、`buildIssueBrief` |
| `frontend/src/views/AiBriefModal.tsx` | 创建 | 任务书弹窗：追加描述、预览、剪贴板复制与降级 |
| `frontend/src/views/PageDetails.tsx` | 修改 | devMode 开关、单条/批量入口、弹窗挂载 |
| `frontend/src/views/ReportDetail.tsx` | 修改 | 透传 sourceDisplay/targetDisplay |
| `frontend/src/features/workbench/pages/workbench-page.tsx` | 修改 | 传入当前选择的文档显示名 |
| `frontend/src/views/HistoryDetail.tsx` | 修改 | 传入记录本身的文档显示名 |
| `frontend/src/workbench.css` | 修改 | 弹窗预览区与开关标签样式 |

---

### 任务 1：ai-brief.ts 纯函数模块

**文件：**
- 创建：`frontend/src/features/workbench/model/ai-brief.ts`

- [ ] **步骤 1：创建模块（完整代码）**

```ts
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
```

- [ ] **步骤 2：构建验证**

运行：`cd frontend && bun run build`
预期：tsc + vite 构建成功，无类型错误。

- [ ] **步骤 3：Commit**

```bash
git add frontend/src/features/workbench/model/ai-brief.ts
git commit -m "feat: AI 排查任务书纯函数模块（开发者模式模型层）"
```

---

### 任务 2：AiBriefModal 弹窗组件与样式

**文件：**
- 创建：`frontend/src/views/AiBriefModal.tsx`
- 修改：`frontend/src/workbench.css`（文件末尾追加）

- [ ] **步骤 1：创建弹窗组件（完整代码）**

```tsx
/** AI 排查任务书弹窗（开发者模式）：追加描述 + 实时预览 + 剪贴板复制。
 *
 * 复制失败（权限/不支持）时降级为预览区手动全选复制；组件不持久化
 * 任何状态，关闭即重置。
 */

import { useEffect, useMemo, useState } from "react"
import { Input, message, Modal, Typography } from "antd"
import type { Issue, QAReport } from "../api"
import { buildIssueBrief, type BriefIssue } from "../features/workbench/model/ai-brief"

export function AiBriefModal({
  open,
  issues,
  report,
  historyRecordId,
  sourceDisplay,
  targetDisplay,
  onClose,
}: {
  open: boolean
  issues: BriefIssue[]
  report: QAReport
  historyRecordId: string | null
  sourceDisplay: string
  targetDisplay: string
  onClose: () => void
}) {
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()

  useEffect(() => {
    if (open) setNote("")
  }, [open])

  const brief = useMemo(
    () =>
      buildIssueBrief({
        report,
        issues,
        historyRecordId,
        sourceDisplay,
        targetDisplay,
        note,
      }),
    [report, issues, historyRecordId, sourceDisplay, targetDisplay, note],
  )

  const copyBrief = async () => {
    setBusy(true)
    try {
      await navigator.clipboard.writeText(brief)
      messageApi.success("任务书已复制，请粘贴到 AI 对话中开始排查")
      onClose()
    } catch {
      messageApi.warning("自动复制失败，请在下方预览区手动全选复制")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      title={`AI 排查任务书（${issues.length} 条）`}
      width={860}
      destroyOnHidden
      onCancel={onClose}
      okText="复制任务书"
      okButtonProps={{ loading: busy }}
      onOk={() => void copyBrief()}
    >
      {contextHolder}
      <Input.TextArea
        aria-label="追加描述"
        placeholder="追加描述（可选）：补充复现步骤、期望行为或业务背景，将原文随任务书提供给 AI…"
        value={note}
        maxLength={2000}
        autoSize={{ minRows: 2, maxRows: 4 }}
        onChange={(event) => setNote(event.target.value)}
      />
      <Typography.Text type="secondary" className="ai-brief-hint">
        任务书包含 issue 完整 metrics 证据、疑似代码位置与本项目的开发契约约定；AI 将按契约排查与修复。
      </Typography.Text>
      <pre className="ai-brief-preview">{brief}</pre>
    </Modal>
  )
}
```

- [ ] **步骤 2：追加样式到 `frontend/src/workbench.css` 末尾**

```css
/* AI 排查任务书弹窗（开发者模式） */
.ai-brief-hint {
  display: block;
  margin-top: var(--qa-space-2, 8px);
  font-size: 12px;
}

.ai-brief-preview {
  max-height: 380px;
  margin: var(--qa-space-2, 8px) 0 0;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--qa-canvas, #f9f9fb);
  border-radius: var(--qa-radius-md, 8px);
}

/* 规则命中列表：开发者模式开关标签 */
.issue-list-dev-toggle {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  color: var(--qa-text-secondary, #5f6b7a);
  cursor: pointer;
}
```

- [ ] **步骤 3：构建验证**

运行：`cd frontend && bun run build`
预期：构建成功。

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/views/AiBriefModal.tsx frontend/src/workbench.css
git commit -m "feat: AI 排查任务书弹窗（追加描述 + 预览 + 剪贴板复制）"
```

---

### 任务 3：PageDetails 集成开关与入口 + 文档显示名透传

**文件：**
- 修改：`frontend/src/views/PageDetails.tsx`
- 修改：`frontend/src/views/ReportDetail.tsx`
- 修改：`frontend/src/features/workbench/pages/workbench-page.tsx`
- 修改：`frontend/src/views/HistoryDetail.tsx`

- [ ] **步骤 1：PageDetails 新增导入**

antd 导入列表（文件顶部 `from "antd"` 的具名导入）中加入 `Switch`；并新增：

```tsx
import { AiBriefModal } from "./AiBriefModal"
import {
  isDevModeEnabled,
  setDevModeEnabled,
  type BriefIssue,
} from "../features/workbench/model/ai-brief"
```

- [ ] **步骤 2：PageDetails 组件新增 props（文档显示名）与状态**

`PageDetails` 的 props 类型追加两个字段，并在函数体加入状态与处理函数：

```tsx
export function PageDetails({
  report,
  rendered,
  taskId,
  historyRecordId,
  decisions,
  onDecide,
  onDecideMany,
  viewState,
  onViewStateChange,
  sourceDisplay,
  targetDisplay,
}: {
  // ……既有 props 保持不变……
  /** 文档对显示名：仅用于任务书环境锚点，由路由页传入。 */
  sourceDisplay: string
  targetDisplay: string
}) {
```

在 `const [batchDecision, setBatchDecision] = ...` 之后加入：

```tsx
  // 开发者模式：AI 排查任务书入口的总开关；持久化到 localStorage，
  // 刷新保持。不属于可分享状态，不进 URL 路由。
  const [devMode, setDevMode] = useState(() => isDevModeEnabled())
  const [briefIssues, setBriefIssues] = useState<BriefIssue[] | null>(null)

  const toggleDevMode = (value: boolean) => {
    setDevMode(value)
    setDevModeEnabled(value)
  }

  const openAiBrief = (issueIds: string[]) => {
    const byId = new Map(allIssues.map((issue) => [issue.id, issue]))
    const targets: BriefIssue[] = issueIds
      .map((id) => byId.get(id))
      .filter((issue): issue is Issue => Boolean(issue))
      .map((issue) => ({ issue, number: (issueNumberById.get(issue.id) ?? 0) + 1 }))
    if (targets.length) setBriefIssues(targets)
  }
```

注意：`openAiBrief` 引用的 `allIssues`/`issueNumberById` 定义在组件更下方（useMemo），需把上述状态与函数放在 `allIssues`/`issueNumberById` 声明**之后**（即 `relatedIssuesFor` 定义之后、`visibleIssues` 之前均可，保证引用顺序合法）。

- [ ] **步骤 3：规则命中列表标题行追加开发者模式开关**

在筛选 `Space`（含问题编号输入、原文筛选、严重度、类型、Segmented）的末尾、`</Space>` 之前追加：

```tsx
          <label className="issue-list-dev-toggle">
            <Switch
              size="small"
              checked={devMode}
              onChange={toggleDevMode}
              aria-label="切换开发者模式"
            />
            开发者模式
          </label>
```

- [ ] **步骤 4：IssueDetails 增加单条入口**

`IssueDetails` props 类型追加 `onAiInvestigate?: () => void`（加入参数解构与类型）；在组件末尾判定按钮 `<Space>` 内、三个判定按钮之后追加：

```tsx
          {onAiInvestigate && (
            <Button size="small" onClick={onAiInvestigate}>
              AI 排查
            </Button>
          )}
```

`expandedRowRender` 中调用处追加透传（devMode 关闭时传 undefined，入口即不渲染）：

```tsx
            <IssueDetails
              issue={issue}
              decisions={decisions}
              onDecide={onDecide}
              onHighlight={(issueId) => highlightIssue(issueId)}
              relatedIssues={relatedIssuesFor(issue)}
              historyRecordId={historyRecordId}
              rendered={rendered}
              onAiInvestigate={devMode ? () => openAiBrief([issue.id]) : undefined}
            />
```

- [ ] **步骤 5：批量操作栏追加批量入口**

批量栏（`selectedIssueIds.length > 0` 的 `issue-batch-bar`）中「取消选择」按钮之前追加：

```tsx
            {devMode && (
              <Button
                size="small"
                onClick={() => openAiBrief(selectedIssueIds)}
              >
                生成 AI 排查任务书
              </Button>
            )}
```

- [ ] **步骤 6：挂载弹窗**

组件返回 JSX 的最外层 `<section className="page-review">` 内、`</section>` 之前追加：

```tsx
      <AiBriefModal
        open={briefIssues !== null}
        issues={briefIssues ?? []}
        report={report}
        historyRecordId={historyRecordId}
        sourceDisplay={sourceDisplay}
        targetDisplay={targetDisplay}
        onClose={() => setBriefIssues(null)}
      />
```

- [ ] **步骤 7：ReportDetail 透传显示名**

`ReportDetail` props 追加 `sourceDisplay?: string` 与 `targetDisplay?: string`（默认 `""`），并在 `<PageDetails …/>` 上透传同名字段。

- [ ] **步骤 8：两个路由页传入显示名**

`workbench-page.tsx` 的 `<ReportDetail …/>` 追加：

```tsx
          sourceDisplay={source.display}
          targetDisplay={target.display}
```

`HistoryDetail.tsx` 的 `<ReportDetail …/>` 追加：

```tsx
          sourceDisplay={full.source_display}
          targetDisplay={full.target_display}
```

- [ ] **步骤 9：构建 + lint 验证**

运行：`cd frontend && bun run build && bun run lint`
预期：构建成功、lint 无错误。

- [ ] **步骤 10：Commit**

```bash
git add frontend/src/views/PageDetails.tsx frontend/src/views/ReportDetail.tsx frontend/src/features/workbench/pages/workbench-page.tsx frontend/src/views/HistoryDetail.tsx
git commit -m "feat: 工作台开发者模式开关与单条/批量 AI 排查入口"
```

---

### 任务 4：手工验收清单

**文件：** 无新改动（如发现问题，修复后重跑本清单并单独 commit）

- [ ] 启动前端（`cd frontend && bun run dev`），打开工作台并载入一份报告（可用「载入示例并试跑」）。
- [ ] 规则命中列表标题行出现「开发者模式」开关，默认关闭；此时展开 issue 无「AI 排查」按钮、勾选多条无任务书按钮。
- [ ] 打开开关：两处入口出现；刷新页面开关仍为开启（localStorage 持久化）。
- [ ] 展开任意 issue →「AI 排查」→ 弹窗标题为「AI 排查任务书（1 条）」；预览含该 issue 的编号、metrics JSON、疑似代码位置与工作约定全文。
- [ ] 在追加描述输入「复现步骤：…」→ 预览「用户追加描述」节实时更新。
- [ ] 点「复制任务书」→ 提示成功、弹窗关闭；粘贴到任意文本编辑器核对内容完整。
- [ ] 勾选 2–3 条 issue → 批量栏「生成 AI 排查任务书」→ 预览含全部所选条目。
- [ ] 关闭开发者模式 → 两处入口立即消失；刷新后仍为关闭。
- [ ] 全量门禁：`cd frontend && bun run build && bun run lint` 通过。

---

## 自检记录

- **规格覆盖度：** 规格 §2 开关（任务 3 步骤 3）、§3 两入口（任务 3 步骤 4/5）、§4 任务书内容（任务 1）、§5 交互与降级（任务 2）、§6 文件清单与状态边界（任务 1–3）、§7 验收（任务 4）——全部有对应任务。
- **占位符扫描：** 无"待定/TODO/类似任务 N"；所有代码步骤含完整代码。
- **类型一致性：** `BriefIssue { issue, number }` 在任务 1 定义、任务 2/3 引用一致；`buildIssueBrief(input: IssueBriefInput): string` 签名唯一；`isDevModeEnabled/setDevModeEnabled` 仅在 ai-brief.ts 定义、PageDetails 调用一致。
