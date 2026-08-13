# Rule Profile 配置契约

## 1. 目的

Rule Profile 将匹配权重、检测器开关、检测阈值和评分规则封装为一个带版本的配置对象。CLI、后续 API 和配置界面必须共用同一个 Pydantic Schema，禁止界面直接编辑 Python 源代码。

## 2. 配置结构

```text
RuleProfile
├── schema_version
├── profile_id / name / version / status
├── matching
│   ├── minimum_score
│   ├── merged_text_coverage_ratio
│   └── weights
├── detectors
│   ├── enabled
│   └── thresholds
└── scoring
    ├── pass_score / fail_score
    ├── critical_forces_fail / high_forces_review
    ├── severity_deductions
    └── issue_type_deduction_caps
```

## 3. 校验规则

- `profile_id` 只允许小写字母、数字和连字符；
- 匹配权重总和必须等于 `1`；
- 严重偏移阈值必须大于普通偏移阈值；
- FAIL 分数线必须低于 PASS 分数线；
- 所有 Severity 必须具有扣分值；
- 所有 IssueType 必须具有页内扣分上限；
- 扣分和扣分上限不能为负数；
- 未声明字段会被拒绝。

## 4. CLI

导出内置配置：

```bash
document-qa --export-default-profile profiles/translation-balanced.v1.json
```

导出 JSON Schema：

```bash
document-qa --export-profile-schema profiles/rule-profile.schema.json
```

使用指定配置执行 QA：

```bash
document-qa source.pdf target.pdf \
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

## 6. 后续 API 映射

后续 FastAPI 层可以直接围绕当前模型提供：

```text
GET  /api/rule-profiles/schema
GET  /api/rule-profiles/default
POST /api/rule-profiles/validate
POST /api/rule-profiles
POST /api/rule-profiles/{id}/versions
```

持久化层必须使用服务端生成的 ID、版本号和原子写入；不得接受客户端提供任意保存路径。

