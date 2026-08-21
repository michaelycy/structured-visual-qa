---
name: develop-document-qa-core
description: Create or review Python behavior in the Structured Visual QA core engine. Use for parsing, grouping, alignment, matching, detection, scoring, schemas, reporting, profiles, pipeline, or CLI changes; use dedicated skills for server orchestration, SQLite migrations, and sample regression diagnosis.
---

# 开发 Document QA Core

在 `core/src/document_qa/` 内修改可独立发行的质检引擎。项目契约中的流水线职责、
数据契约、审批规则和编码规范均为前置约束。

## 开始前

1. 检查目标模块、调用链、`RuleProfile`、相关 Schema 和当前样例行为。
2. 确定影响阶段：parse、group、alignment、match、detect、score 或 report。
3. 编辑前说明目标、不变量、阈值归属、兼容影响和验证路径。

具体文档偏差先使用 `diagnose-document-regression` 定位，不从最终截图或 Issue 猜测根因。

## 核心规则

- 保持项目契约定义的 Parser → Grouper → Aligner → Matcher → Detector → Scorer → Reporter 边界；
- core 不得导入 HTTP、server 或 SQLite 依赖；PyMuPDF 对象不得泄漏出解析/渲染边界；
- 所有阈值、权重、严重度映射和扣分上限只进入 `RuleProfile`；
- 禁止在 Detector、Matcher、CLI 或 Reporter 中新增散落阈值；
- 契约列出的破坏性变更必须先说明影响并等待确认；
- 单样本修复不得按文件名硬编码，必须推演其他布局、语言对和既有 Issue。

## Issue 与 Schema 联动

新增或改变 Issue 时检查：

- Schema、`RuleProfile`、Scorer 和 Reporter；
- API/前端展示和历史报告兼容；
- BBox、可读描述以及参与判定的 `metrics`；
- `QAReport` JSON 能否重新通过当前 Schema 校验。

## 验证

执行 `AGENTS.md` 的编译和真实样例分阶段验证，并额外：

- 对修改点推演阳性、阴性、边界和既有行为不变量；
- 权重或严重度变化附 Golden Sample 前后差异；
- 从首个受影响阶段开始检查，但仍完成后续报告链路。
