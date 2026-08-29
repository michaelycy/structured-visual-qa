# 工作台开发者模式：AI 排查任务书 设计规格

日期：2026-08-28 ｜ 状态：待用户审查 ｜ 范围：纯前端（frontend/）

## 1. 背景与目标

工作台的「规则命中列表」是质检问题的唯一逐条视图。当前把问题交给 AI
（DSH 代理）排查需要人工拼装上下文。本功能在开发者模式下提供：

- 选中单条 issue → 追加描述 → 一键生成「排查任务书」并复制到剪贴板；
- 勾选多条 issue → 生成合并任务书（同一根因引发的一簇问题）；
- 用户把任务书粘贴到 DSH 对话，AI 按项目契约直接排查与修复。

**决策记录**：交接方式=剪贴板复制（零后端改动）；范围=单条+批量多选；
实现=纯前端生成（方案 A），检测器诊断映射在前端镜像 server 端
`_DETECTOR_DIAGNOSTICS` 并注释标注同步来源。已否决：服务端写文件、
服务端自动调 AI（违反契约 §3.2）。

## 2. 开发者模式开关

- 位置：工作台「规则命中列表」标题行右侧（筛选区旁），`Switch` + 文案
  「开发者模式」。
- 关闭时所有 AI 排查入口完全不渲染（不是隐藏，是不渲染）。
- 持久化：`localStorage`，key `qa.devMode`；默认关闭；不进 URL 路由
  （非可分享状态，不属于一级页面状态）。

## 3. 入口

| 入口 | 位置 | 行为 |
| --- | --- | --- |
| 单条 | `IssueDetails` 展开详情操作区（三个判定按钮旁） | 「AI 排查」按钮，携带该 issue |
| 批量 | 批量操作栏（`issue-batch-bar`） | 「生成 AI 排查任务书」，携带当前勾选的全部 issue |

弹窗状态由 `PageDetails` 持有；`IssueDetails` 只接收回调，不持有 Modal。

## 4. 任务书内容（`features/workbench/model/ai-brief.ts` 纯函数）

输出 Markdown，结构固定如下：

1. **任务**：针对下列 issue 完成根因排查。执行前先独立评估：issue 是否
   真实缺陷（还是误报/正常排版适配），以及用户追加描述是否成立——若用户
   理解有误，直接反驳并给出依据，不要附和执行。确认代码缺陷后按最佳实践
   修复；确认检测逻辑正确则给出误报原因与证据。附用户追加描述原文（可为空）。
2. **环境锚点**：历史记录 ID 与取报告接口（`GET /api/history/item/{id}`）、
   文档对显示名、目标文档页码；无历史锚点时标注「以当前报告数据为准」。
3. **Issue 明细**（每条）：全报告连续编号、类型/严重度/检测器、页码、
   bbox、描述、原文/译文证据文本、metrics 完整 JSON（代码块）。
4. **疑似阶段与代码检索起点**：按 issue 的 detector 映射（镜像 server 端
   `review_insight_service._DETECTOR_DIAGNOSTICS`，文件头注释要求两处同步）。
5. **工作约定（强制，逐条写入任务书）**：
   - 以 `docs/project-contract.md` 与 `AGENTS.md` 为基线：契约优先，认为
     契约有问题先提请用户确认，不得绕过；
   - 执行任何修复前，先从专业角度独立评估：(1) issue 本身是否为真实缺陷
     （还是检测器误报、正常翻译排版适配或已知容差场景）；(2) 用户追加
     描述是否成立。若用户理解有误，必须直接反驳并给出可验证依据
     （metrics 数值、契约条款、PDF 实际渲染效果、排版领域惯例），不得
     为了顺从而附和执行；
   - 先复现诊断（`document-qa --verify-stage` 分阶段 / `tests/` 定向用例），
     确认根因后再动手；**不得以降级严重度、放宽阈值或跳过测试掩盖问题**；
   - 遵守分层边界：core 零 HTTP、禁止 import server/persistence；
     `api → services → core`；frontend 组件禁止直接 `fetch`；
   - 检测阈值与权重只能写入 `RuleProfile`；触碰 §12（删除公开字段、匹配
     权重、严重度阈值、换 PDF 引擎）必须先说明影响并等用户确认；
   - **代码设计与拆分要求**：单一职责、模块边界清晰；新增能力先进
     core/对应 feature；公共类/函数写中文 Docstring；主要逻辑用中文注释
     解释设计目的；标识符与公开 JSON 字段用英文；禁止无关重构与全局
     格式化；大文件顺手做与当前任务相关的合理拆分，不做无关迁移；
   - 完成后验收：`uv lock --check`、`ruff check`、渐进 mypy、
     `compileall`、双包构建；涉及检测行为时逐阶段展示
     parse→group→alignment→match→detect→report 摘要并等用户确认；
     逐条说明行为不变式。

## 5. 交互与错误处理

- `views/AiBriefModal.tsx`：追加描述 `TextArea`（最多 2000 字）+ 任务书
  实时预览（只读 `<pre>`）+「复制任务书」主按钮。
- 复制走 `navigator.clipboard.writeText`；异常（权限/不支持）降级为
  预览区可选中并 message 提示手动复制，不阻塞。
- clipboard 在 127.0.0.1（secure context）可用；仍按失败降级实现。

## 6. 组件与文件清单

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `frontend/src/features/workbench/model/ai-brief.ts` | 新增 | 纯函数：`buildIssueBrief(input)` 组装 markdown；诊断映射常量 |
| `frontend/src/views/AiBriefModal.tsx` | 新增 | 任务书弹窗：描述输入、预览、复制与降级 |
| `frontend/src/views/PageDetails.tsx` | 修改 | devMode 开关与持久化、两个入口按钮、弹窗挂载与状态 |

状态边界：`devMode` 为 PageDetails 本地状态（localStorage 同步），不进
workbench context、不进路由；批量勾选复用现有 `selectedIssueIds`。

## 7. 验收

- `bun run build`（tsc + vite）与 `bun run lint`（oxlint）通过；
- 手工验收清单：开关刷新后保持；关闭后单条/批量入口消失；单条任务书含
  完整 metrics 与证据；批量任务书含全部所选条目；追加描述原文进入任务书；
  剪贴板失败时降级可复制；
- 不触碰后端、契约、锁文件；无新增依赖。
