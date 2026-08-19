# document-qa MCP 服务接入指南

把翻译文档 QA 能力以 MCP（Model Context Protocol）暴露给 LLM 客户端。
传输：**stdio**；工具：12 个（比较/历史/报告/导出/验证/Profile/术语库/引擎探测）。

## 前置

```bash
cd /path/to/structured-visual-QA
.venv/bin/python -m pip install -e core -e ".[mcp]"
```

## 客户端配置

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "document-qa": {
      "command": "/path/to/structured-visual-QA/.venv/bin/document-qa-mcp",
      "cwd": "/path/to/structured-visual-QA",
      "env": {
        "DQA_SAMPLES_DIR": "/path/to/structured-visual-QA/examples"
      }
    }
  }
}
```

### Cursor

`.cursor/mcp.json`（项目级）或全局配置：

```json
{
  "mcpServers": {
    "document-qa": {
      "command": "/path/to/structured-visual-QA/.venv/bin/document-qa-mcp",
      "cwd": "/path/to/structured-visual-QA"
    }
  }
}
```

### 通用（任何 stdio MCP 客户端）

启动命令：`document-qa-mcp`（等价 `python -m document_qa_server.mcp_server`），
在项目根运行；环境变量走 `DQA_*` 前缀（见 `.env.example`）。

## 工具清单

| 工具 | 用途 |
| --- | --- |
| `compare_documents` | 比较两份文档（PDF/Office），返回摘要 + history_record_id |
| `list_history` | 历史比较记录（时间倒序前 30 条） |
| `get_report` | 完整报告；`page` 参数取单页明细 |
| `export_report` | 导出 XLSX/HTML 交付物，返回文件路径 |
| `verify_stage` | 分阶段验证（parse→…→report），调试与教学 |
| `list_profiles` / `get_profile` / `save_profile` | 规则配置管理 |
| `list_glossaries` / `get_glossary` / `save_glossary` | 术语库管理 |
| `engine_status` | LibreOffice 归一化引擎与格式支持探测 |

## 输出裁剪原则

LLM 上下文有限：`compare_documents` 默认返回摘要（状态/分数/issue 计数/
前 10 条问题），完整明细通过 `get_report` 按页获取。导出产物落本地文件，
MCP 只回路径——大内容永远不进上下文。

## 与 Web/API 的关系

三者共用同一套 server 层服务与 core 引擎：

```
webapp（浏览器） ──HTTP──▶ api 路由 ──▶ services ──▶ core
MCP 客户端（LLM）──stdio──▶ mcp_server ──┘
CLI ─────────────────────────────────────┘
```

MCP 进程是 services 的库消费者，不经过 HTTP；历史记录与 Web 界面互通
（同一 `webapp-artifacts/history/`）。
