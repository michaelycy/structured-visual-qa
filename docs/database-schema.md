# SQLite 业务数据结构

## 存储边界

数据库文件默认位于 `webapp-artifacts/metadata.sqlite3`。SQLite 是样本、配置、
对比记录、完整报告和人工复核的事实来源；PDF、Office 文档、页面 PNG 与导出
文件仍保存在文件系统中，`stored_files` 只登记其元数据和绝对路径。

数据库启动时统一开启：

- `journal_mode = WAL`：允许多进程读与单写事务协调；
- `foreign_keys = ON`：每个连接都强制外键；
- `busy_timeout = 10000`：写锁竞争最多等待 10 秒；
- 版本化迁移：`PRAGMA user_version` 与 `schema_migrations` 双重记录。

## 表及职责

| 表 | 作用 |
| --- | --- |
| `stored_files` | 登记文档摘要、名称、格式、大小、路径及可用状态 |
| `samples` | 保存一组可复用的源/目标文档及其 BCP 47 语言对 |
| `rule_profile_versions` | 保存不可变寻址的规则配置版本及完整 JSON |
| `glossary_versions` | 保存不可变寻址的术语库版本及完整 JSON |
| `comparison_records` | 保存对比历史的高频查询摘要和文件、样本、规则关联 |
| `comparison_reports` | 与对比记录一对一保存完整 `QAReport` JSON |
| `comparison_glossaries` | 保存对比记录实际使用的术语库版本外键 |
| `review_tasks` | 保存人工复核任务的报告身份快照 |
| `review_decisions` | 保存逐 Issue 的确认、误报或忽略结论 |
| `schema_migrations` | 记录已经应用的数据库结构迁移 |
| `legacy_imports` | 审计旧 JSON 的一次性导入数量 |
| `schema_descriptions` | 数据库内可查询的逐表、逐字段中文数据字典 |

## 主要关系

```text
stored_files ──< samples >── stored_files
     │                         │
     └────< comparison_records >──── rule_profile_versions
                    │
                    ├── comparison_reports（1:1，完整 QAReport）
                    └── comparison_glossaries ── glossary_versions

review_tasks ──< review_decisions
```

样本、规则和术语库的“删除”采用归档，不物理删除被历史引用的数据。删除
`comparison_records` 时，完整报告和术语关联按外键级联删除；输入文件元数据、
样本、规则及术语版本不会级联删除。

## 查询字段注释

SQLite 不支持 `COMMENT ON TABLE/COLUMN`。项目使用两层注释：

1. `server/src/document_qa_server/persistence/database.py` 的建表 SQL 保留中文注释；
2. `schema_descriptions` 保存每张表和每个字段的中文说明。

查询全部字段说明：

```sql
SELECT table_name, column_name, description
FROM schema_descriptions
ORDER BY table_name, column_name;
```

查询指定表：

```sql
SELECT column_name, description
FROM schema_descriptions
WHERE table_name = 'comparison_records'
ORDER BY column_name;
```

## 完整性检查

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
PRAGMA user_version;
```

`integrity_check` 应返回 `ok`，`foreign_key_check` 应返回空结果。对比成功时，
`comparison_records`、`comparison_reports` 和可选的
`comparison_glossaries` 在同一事务中写入，任一写入失败都会整体回滚。
