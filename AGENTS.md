# AGENTS.md

本项目一切编码工作以 **docs/project-contract.md** 为基线契约，开始任何编码任务前必须先读取它。

## 强制规则

1. **契约优先**：产品边界（§3）、组件职责（§7）、数据契约（§6）与变更规则（§12）冲突时，以契约为准；认为契约本身有问题时，先提出修改建议并等确认，不要绕过。
2. **破坏性变更需审批**：触碰 §12 列出的内容（删除/重命名公开字段、匹配权重、严重度阈值、更换 PDF 引擎）时，先说明影响并等待用户确认。
3. **阈值集中管理**：所有检测阈值和权重只写入 `src/document_qa/profiles.py` 的 `RuleProfile`，禁止散落在 CLI、检测器或报告代码中。
4. **真实样例分阶段验证**：开发完成后不运行 unittest 验证，而是用 `--verify-stage` 在真实 PDF 对（默认 `examples/` 样例）上逐阶段验证：parse → group → alignment → match → detect → report。每个阶段向用户展示摘要（页数/Region 数/配对数/Issue 数/分数），**等待用户确认后再进入下一阶段**。unittest 仅在用户明确要求时运行。
5. **编码约定**：公共类/函数中文 Docstring，主要逻辑处中文注释解释设计目的；标识符和公开 JSON 字段用英文；禁止无关重构和全局格式化。
6. **验收标准**：编码完成后按契约 §11 自查——`python -m compileall -q src tests` 通过 + 分阶段验证各阶段摘要符合预期 + 修改点的行为不变式逐条推演说明。

## 常用命令

```bash
# 分阶段验证（开发后的标准验证方式，逐阶段交互确认）
PYTHONPATH=src .venv/bin/python -m document_qa examples/un-china-2024-en.pdf examples/un-china-2024-zh.pdf \
  --verify-stage report --verify-dir tmp/verify-stages

# 界面化：API 服务（127.0.0.1:8765）
PYTHONPATH=src .venv/bin/python -m uvicorn document_qa.server:app --port 8765
# 界面化：前端开发服务器（127.0.0.1:5180，/api 已代理）
cd webapp && bun run dev
# 前端类型检查与构建
cd webapp && bun run build

PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests
PYTHONPATH=src .venv/bin/python -m document_qa examples/un-china-2024-en.pdf examples/un-china-2024-zh.pdf --output tmp/qa-report.json
```

## 后端分层（界面化增补）

依赖方向恒为 `api/ → services/ → 核心引擎`：api 层只做协议转换（DTO、状态码、静态挂载）；services 层做用例编排（互斥锁、产物目录）；核心引擎不感知 HTTP，禁止 import fastapi/api/services。详见 docs/project-contract.md §7。
