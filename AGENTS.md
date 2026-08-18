# AGENTS.md

本项目一切编码工作以 **docs/project-contract.md** 为基线契约，开始任何编码任务前必须先读取它。

## 强制规则

1. **契约优先**：产品边界（§3）、组件职责（§7）、数据契约（§6）与变更规则（§12）冲突时，以契约为准；认为契约本身有问题时，先提出修改建议并等确认，不要绕过。
2. **破坏性变更需审批**：触碰 §12 列出的内容（删除/重命名公开字段、匹配权重、严重度阈值、更换 PDF 引擎）时，先说明影响并等待用户确认。
3. **阈值集中管理**：所有检测阈值和权重只写入 `src/document_qa/profiles.py` 的 `RuleProfile`，禁止散落在 CLI、检测器或报告代码中。
4. **真实样例分阶段验证**：开发完成后不运行 unittest 验证，而是用 `--verify-stage` 在真实 PDF 对（默认 `examples/` 样例）上逐阶段验证：parse → group → alignment → match → detect → report。每个阶段向用户展示摘要（页数/Region 数/配对数/Issue 数/分数），**等待用户确认后再进入下一阶段**。unittest 仅在用户明确要求时运行。
5. **编码约定**：公共类/函数中文 Docstring，主要逻辑处中文注释解释设计目的；标识符和公开 JSON 字段用英文；禁止无关重构和全局格式化。
6. **验收标准**：编码完成后按契约 §11 自查——`python -m compileall -q src tests` 通过 + 分阶段验证各阶段摘要符合预期 + 修改点的行为不变式逐条推演说明。

## 仓库结构（双包拆分）

- `core/`：**document-qa** 核心引擎发行包（解析/分组/对齐/匹配/检测/评分/报告 + `document-qa` CLI），零 HTTP 依赖，可独立安装给其他系统复用
- `server/`：**document-qa-server** 服务发行包（api 协议层 + services 应用层），依赖 core；入口 `document-qa-server`
- `webapp/`：React+Vite+TS 前端
- 依赖方向恒为 `webapp → server(api → services) → core`；core 禁止 import fastapi/uvicorn 或 server 包

## 常用命令

```bash
# 安装双包（core 先装）
.venv/bin/python -m pip install -e core -e server

# core CLI：比较与分阶段验证（无需 PYTHONPATH）
.venv/bin/document-qa examples/un-china-2024-en.pdf examples/un-china-2024-zh.pdf --output tmp/qa-report.json
.venv/bin/document-qa examples/un-china-2024-en.pdf examples/un-china-2024-zh.pdf --verify-stage report --verify-dir tmp/verify-stages

# 界面化：API 服务（127.0.0.1:8765）与前端（127.0.0.1:5180，/api 已代理）
.venv/bin/document-qa-server --port 8765
cd webapp && bun run dev
cd webapp && bun run build

PYTHONPATH=core/src .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q core/src server/src tests
```

## 分层纪律

- `server/api/` 只做协议转换（DTO、状态码、静态挂载）；`server/services/` 做用例编排（互斥锁、产物目录）
- core 不感知 HTTP；新增核心能力先进 core，服务层只做包装
- 详见 docs/project-contract.md §7
