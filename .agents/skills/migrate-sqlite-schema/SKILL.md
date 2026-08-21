---
name: migrate-sqlite-schema
description: Design or review SQLite schema and persistence migrations in the Structured Visual QA server. Use for tables, columns, indexes, constraints, schema versions, data dictionaries, legacy imports, or transactional QAReport persistence; not for service-only changes.
---

# 迁移 SQLite Schema

在 `server/src/document_qa_server/persistence/` 中安全演进 SQLite，保持迁移单向、幂等、
可审计且不丢失旧数据。

## 开始前

完整读取 `persistence/database.py`、目标 Service 和相关 API DTO；检查
`SCHEMA_VERSION`、全部已发布迁移、`SCHEMA_DESCRIPTIONS`、外键和事务调用方。编辑前
说明结构变化、升级路径、数据风险、兼容策略和验证矩阵。

删除、重命名、重写既有字段或可能丢失数据时，先等待用户确认。Service-only 修改使用
`develop-server-use-case`。

## 迁移规则

- 只追加迁移，不修改已发布的 `_migration_N`；
- `SCHEMA_VERSION` 单调递增，同步记录 `schema_migrations` 和 `PRAGMA user_version`；
- 空库能连续应用全部迁移，旧库能跳过已应用版本；
- 重复初始化不得重复导入、重复建索引或覆盖业务状态；
- 禁止删除数据库、重建整库或静默丢弃旧 JSON；
- 遗留导入使用稳定 import key，结果可审计，失败不得标记完成。

## 结构与数据不变量

新增表或字段时同步提供：

- SQL 中文用途注释；
- `SCHEMA_DESCRIPTIONS` 的表及逐字段说明；
- 主键、唯一性、空值、`CHECK`、索引、外键及 `ON DELETE` 设计。

保持外键开启、WAL、busy timeout 和显式事务。文件二进制仍保存在文件系统；对比摘要与
完整 `QAReport` 必须原子提交，读回后重新通过当前 Schema 校验。

## 验证矩阵

只使用临时目录和临时数据库验证：

1. 空库创建与完整数据字典；
2. 重复初始化无副作用；
3. 前一版本升级且旧数据保留；
4. 外键、唯一性、`CHECK` 和删除策略；
5. 异常回滚后的事务原子性；
6. 完整报告写入、读回和 Schema 校验；
7. 遗留导入重复执行不覆盖新状态。

最后执行 `AGENTS.md` 的通用验证；若影响对比持久化，还要完成最终入库检查。
