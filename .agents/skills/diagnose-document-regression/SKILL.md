---
name: diagnose-document-regression
description: Reproduce and localize an unexpected result for a real document pair, golden sample, QA report, issue record, or missing history entry in Structured Visual QA. Use staged evidence across core, server, persistence, and frontend; implement a fix only when requested.
---

# 诊断文档回归

针对真实源/目标文档逐阶段定位偏差，先确定首个异常层级，再决定是否修改代码。

## 建立基线

确认文件、语言对、规则配置、术语库、历史报告和期望行为；记录工作树与基线来源，区分
原始 PDF 和 Office 归一化结果。诊断产物写入 `tmp/` 或用户指定目录，不覆盖样本。

只要求分析时保持只读；同时要求修复时也必须先定位阶段。

## 分阶段诊断

按 `AGENTS.md` 的确认节奏依次检查：

1. **parse**：页数、尺寸、Block 数和类型，文本、图片、隐形文字或转曲情况；
2. **group**：Region 数、类型、关键 BBox 和错误合并/拆分；
3. **alignment**：页面配对、源缺失页和目标新增页；
4. **match**：每页配对数、未配对 Region 和平均匹配分；
5. **detect**：Issue 类型、严重度、BBox 和判定 metrics；
6. **report**：分数、状态、摘要计数和导出一致性。

使用 `document-qa --verify-stage <stage> --verify-dir <dir>`，不得跳到 report 后反推，也
不得在等待用户确认时继续下一阶段。

## 跨层追踪

core 报告正确但系统记录异常时，继续检查：

```text
QAReport → CompareService → task status
         → CompareHistoryService transaction
         → comparison_records + comparison_reports
         → history API → frontend Query
```

区分 Issue 未产生、报告过滤、任务未完成、入库失败、API/缓存未刷新，以及用户仅停止
等待但服务端仍运行等情况。

## 结论与分流

结论包含复现条件、基线、首个偏差阶段、实际/期望值、证据、根因层级、影响范围、
未证实推断和最小修复方向。“未发现”不得写成“系统不存在”。

- core 流水线 → `develop-document-qa-core`；
- Route、任务或 Service → `develop-server-use-case`；
- Schema、迁移或事务 → `migrate-sqlite-schema`；
- 前端 Router、Query 或状态 → `create-react-feature`；
- 纯展示 → `create-pure-component`。

修复后从首个受影响阶段重新验证并完成后续链路；诊断产物不得进入版本控制。
