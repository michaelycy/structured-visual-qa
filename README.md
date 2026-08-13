# Structured Visual QA

Structured Visual QA 用于比较源 PDF 与翻译后 PDF 的结构和视觉保真度。系统以确定性数据为底座，输出区域匹配、结构化差异、问题严重度、页面评分和文档状态。

## 当前能力

- 使用 PyMuPDF 提取文本 Span、字体、BBox 和图片；
- 将原始 Block 组合为可比较 Region；
- 使用 SciPy 全局最优分配完成同页 Region 对齐；
- 检测缺失元素、额外元素、区域偏移、字号缩小、越界和重叠；
- 输出经过 Pydantic Schema 校验的 JSON 报告；
- 可选渲染源文档和目标文档页面 PNG。

## 安装

建议创建独立虚拟环境：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
```

## 使用

```bash
document-qa source.pdf target.pdf \
  --output artifacts/qa-report.json \
  --render-dir artifacts/pages
```

也可以直接运行模块：

```bash
python -m document_qa source.pdf target.pdf --output qa-report.json
```

返回的状态包括：

- `pass`：没有 High/Critical 且得分不低于 90；
- `review`：存在 High，或分数低于 90；
- `fail`：存在 Critical，或分数低于 75。

## 开发验证

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
```

## 许可证提示

本项目选择 PyMuPDF 作为 PDF 引擎。PyMuPDF 开源版本使用 AGPL v3；闭源或商业使用前必须完成许可证评估或取得商业许可证。详细约束见 `docs/project-contract.md`。

