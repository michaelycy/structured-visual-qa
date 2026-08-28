# Rule Profile 配置契约

## 1. 目的

Rule Profile 将匹配权重、检测器开关、检测阈值和评分规则封装为一个带版本的配置对象。CLI、API 和 Web 配置界面共用同一个 Pydantic Schema，禁止界面直接编辑 Python 源代码。完整字段以 `RuleProfile` 导出的默认 JSON 和 JSON Schema 为准，本文只描述稳定结构。

## 2. 配置结构

```text
RuleProfile
├── schema_version
├── profile_id / name / version / status / description
├── matching
│   ├── minimum_score
│   ├── merged_text_coverage_ratio
│   ├── text_type_similarity
│   ├── weights
│   └── logical_grouping
│       ├── enabled / max_regions
│       ├── line_gap_ratio / horizontal_overlap_ratio
│       ├── font_size_tolerance_ratio / edge_tolerance_ratio / negative_overlap_ratio
│       └── counterpart_overlap_ratio
├── alignment
│   ├── enabled
│   └── max_shift / skip_penalty / shift_margin
├── grouping
│   ├── heading_ratio
│   ├── disconnected_span_gap_ratio
│   └── style_font_size_tolerance_ratio / style_font_size_tolerance_points
├── detectors
│   ├── enabled
│   ├── thresholds
│   ├── severity_overrides
│   └── layout_analog_weights
└── scoring
    ├── pass_score / fail_score
    ├── critical_forces_fail / high_forces_review
    ├── severity_deductions
    └── issue_type_deduction_caps
```

## 3. 校验规则

- `profile_id` 只允许小写字母、数字和连字符；
- 匹配权重总和必须等于 `1`；
- 版面类比（layout analog）权重总和必须等于 `1`；
- 严重偏移阈值必须大于普通偏移阈值；
- FAIL 分数线必须低于 PASS 分数线；
- 所有 Severity 必须具有扣分值；
- 所有 IssueType 必须具有页内扣分上限；
- 扣分和扣分上限不能为负数；
- 未声明字段会被拒绝。

## 4. CLI

导出内置配置：

```bash
uv run document-qa --export-default-profile profiles/translation-balanced.v1.json
```

导出 JSON Schema：

```bash
uv run document-qa --export-profile-schema profiles/rule-profile.schema.json
```

使用指定配置执行 QA：

```bash
uv run document-qa source.pdf target.pdf \
  --profile profiles/translation-balanced.v1.json \
  --output artifacts/report.json
```

## 5. UI 接入约束

配置界面应从 JSON Schema 获取字段类型、范围和枚举，并提供额外的人类可读说明。保存配置时必须把完整 JSON 交给后端的 `RuleProfile` 校验，前端校验不能替代服务端校验。

发布已存在的 Profile 时应创建新版本，而不是覆盖旧 JSON。每个 QA 报告都会保存：

```text
rule_profile_reference
rule_profile_snapshot
```

因此旧报告不依赖当前 Profile 状态，可以准确复现运行规则。

## 6. API 映射（已落地）

server 层已提供以下 Profile 路由（`server/src/document_qa_server/api/routes_profile.py`）：

```text
GET    /api/profile/default
GET    /api/profile/schema
GET    /api/profile/list
GET    /api/profile/item/{filename}
POST   /api/profile/save
POST   /api/profile/item/{filename}/publish
DELETE /api/profile/item/{filename}
```

Profile 由服务端按 `profile_id` 与 `version` 生成兼容文件名，正文、摘要与状态保存在
SQLite `rule_profile_versions` 中并通过事务写入；客户端不能指定服务器保存路径。
发布操作创建或更新不可覆盖的已发布版本语义，历史报告继续引用任务执行时内嵌的
Profile 快照。
