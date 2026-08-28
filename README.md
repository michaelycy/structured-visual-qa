# Structured Visual QA

Structured Visual QA 用于比较源 PDF 与翻译后 PDF 的结构和视觉保真度。系统以确定性数据为底座，输出区域匹配、结构化差异、问题严重度、页面评分和文档状态。

## 当前能力

- 使用 PyMuPDF 提取文本 Span、字体、透明度、BBox、图片及内容指纹；
- 将原始 Block 组合为 Region，并通过跨页对齐和 SciPy 全局最优分配建立对应关系；
- 检测页面/元素缺失、偏移与缩放、字号变化、对齐变化、越界、重叠、隐形文字、
  文字转曲/栅格化、数字不一致、漏译和术语违规；
- 可选使用本地 PaddleOCR 检查大图片候选区中的源语言残留，默认关闭且失败可降级；
- server 支持 PDF 与 Office 文档归一化、异步任务、SQLite 历史/样本/Profile/复核、
  XLSX/HTML 导出和 MCP stdio 接入；
- 输出经过 Pydantic Schema 校验且内嵌 Rule Profile 快照的 JSON 报告，并可渲染
  源/目标页面 PNG 作为复核证据。

## 安装

推荐使用仓库根的 uv workspace，同步 core、server 与开发工具：

```bash
uv sync --locked --all-packages --group dev
```

只安装需要的可选能力：MCP 增加 `--extra mcp`，PaddleOCR 增加
`--extra ocr-paddle`；两者都需要时可重复传入两个 `--extra`。

如不使用 uv，可按发行包依赖方向安装：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e core -e server
```

## 使用

```bash
uv run document-qa source.pdf target.pdf \
  --output artifacts/qa-report.json \
  --render-dir artifacts/pages
```

导出内置规则配置：

```bash
uv run document-qa --export-default-profile profiles/translation-balanced.v1.json
```

导出供配置界面生成表单的 JSON Schema：

```bash
uv run document-qa --export-profile-schema profiles/rule-profile.schema.json
```

使用经过界面或人工编辑并校验的规则配置：

```bash
uv run document-qa source.pdf target.pdf \
  --profile profiles/translation-balanced.v1.json \
  --output artifacts/qa-report.json
```

每份 QA 报告都会保存 Profile 版本引用和完整快照，后续修改配置不会影响旧任务复现。

也可以直接运行模块：

```bash
uv run python -m document_qa source.pdf target.pdf --output qa-report.json
```

返回的状态包括：

- `pass`：没有 High/Critical 且得分不低于 90；
- `review`：存在 High，或得分处于 75 至 90；
- `fail`：存在 Critical，或得分低于 75。

## 启动服务

### 后端服务

启动 FastAPI 服务器（默认端口 8765）：

```bash
uv run document-qa-server --port 8765
```

服务器启动后可访问：
- API 文档：http://127.0.0.1:8765/docs
- OpenAPI 规范：http://127.0.0.1:8765/openapi.json

### 前端服务

启动 React+Vite 开发服务器：

```bash
cd frontend && bun run dev
```

前端服务默认运行在 http://localhost:5180/，会自动代理 `/api` 请求到后端服务。

### 完整启动流程

在两个终端分别启动服务：

```bash
# 终端 1：启动后端
uv run document-qa-server --port 8765

# 终端 2：启动前端
cd frontend && bun run dev
```

启动完成后访问 http://localhost:5180/ 即可使用 Web 界面。

## 开发验证

```bash
uv lock --check
uv run ruff check core/src server/src tests
uv run mypy core/src/document_qa/schemas core/src/document_qa/profiles.py \
  server/src/document_qa_server/persistence server/src/document_qa_server/settings.py
uv run python -m compileall -q core/src server/src tests
uv run python -m unittest discover -s tests -v
```

涉及检测行为的改动还必须使用 `document-qa --verify-stage` 对 `examples/`
真实 PDF 对依次执行 parse → group → alignment → match → detect → report，
并按项目契约在阶段之间人工确认摘要。

## 许可证提示

本项目选择 PyMuPDF 作为 PDF 引擎。PyMuPDF 开源版本使用 AGPL v3；闭源或商业使用前必须完成许可证评估或取得商业许可证。详细约束见 `docs/project-contract.md`。
