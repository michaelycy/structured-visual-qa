---
name: develop-server-use-case
description: Create or review a Structured Visual QA Python server use case involving FastAPI routes, DTOs, application services, tasks, files, normalization, history, profiles, glossaries, reviews, or MCP wrappers. Use dedicated skills for core detection behavior and SQLite schema changes.
---

# 开发 Server 用例

在 `server/src/document_qa_server/` 内实现 HTTP 或应用服务能力。依赖关系为：

```text
api → services → core
            ↘ persistence
```

`persistence` 不调用 core；Service 负责协调二者。

## 开始前

追踪目标 Route、DTO、Service、Persistence 和 core 公共入口，并检查路由注册、settings、
任务状态、产物目录和错误映射。编辑前说明协议变化、用例流程、失败路径、持久化影响和
保持不变的 API 行为。

核心检测变化使用 `develop-document-qa-core`；表、字段、索引或迁移变化同时使用
`migrate-sqlite-schema`；具体文档回归先使用 `diagnose-document-regression`。

## 分层边界

| 层 | 负责 | 禁止 |
| --- | --- | --- |
| `api/` | DTO、上传协议、状态码、响应转换、路由注册 | 检测算法、事务、产物编排 |
| `services/` | 用例、锁、任务、目录、core 与 persistence 协调 | 感知 HTTP Request/Response |
| `persistence/` | SQLite 连接、事务、查询和迁移 | 调用检测流水线 |

API Route 只调用 Service；Service 返回核心模型或纯数据；API DTO 与 core Schema 在协议
边界显式转换；MCP 只包装现有 Service，不建立第二套业务实现。

## 用例检查

按任务相关性明确：

- 输入、默认值、文件限制和校验错误；
- 同步结果与异步任务响应；
- queued、running、done、error 状态与终止条件；
- 超时、重复提交、锁冲突、解析失败和产物缺失；
- 事务边界、失败回滚、HTTP 状态码和用户可读错误。

上传输入始终不可信；未经授权不得放宽 CORS、文件限制或静态目录。停止前端等待不等于
取消服务端任务，没有取消协议时保持两者语义分离。

## 验证

执行 `AGENTS.md` 的通用验证，并用临时目录检查目标 Route/Service 的成功、校验失败和
服务异常路径。涉及任务时检查状态转换；涉及报告时验证 `QAReport`；涉及对比链路时
按项目规定完成真实样例分阶段验证。
