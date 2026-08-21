# Structured Visual QA 项目契约

## 1. 契约目的

本文档定义 Structured Visual QA 项目的产品边界、架构边界、数据约束、质量门槛和变更规则。它是团队进行实现、评审和验收的共同基线，不是法律合同。

## 2. 项目目标

系统比较源 PDF 与翻译后 PDF，回答以下问题：

- 页面和主要元素是否完整；
- 对应区域是否发生异常偏移、缩放或样式变化；
- 是否出现文字越界、区域重叠、图片缺失等交付风险；
- 异常位于哪一页、哪个区域，严重程度如何；
- 文档最终应判定为 `PASS`、`REVIEW` 还是 `FAIL`。

系统必须输出可复核的结构化证据，不以单一图片相似度或单次大模型判断作为最终依据。

## 3. MVP 范围

### 3.1 包含

- 机器生成型 PDF；
- PDF 页面、文本 Span、图片和基础样式解析；
- PDF 页面 PNG 渲染；
- Block 到 Region 的规则分组；
- 同页 Region 匹配；
- 缺失元素、位置偏移、内容越界、区域重叠和字号缩小检测；
- 文档评分及 `PASS / REVIEW / FAIL` 判定；
- JSON 报告与命令行入口。

### 3.2 暂不包含

- DOCX、PPTX、XLSX 等 Office 格式的原生结构解析（多格式经 LibreOffice 归一化支持，原生解析仍排除）；
- 扫描 PDF 的自动 OCR；
- 复杂表格结构恢复；
- 远程数据库、对象存储和任务队列；server 可使用嵌入式 SQLite 保存
  样本、配置、复核与完整报告等业务数据，原始文档和渲染产物仍存文件系统；
- 多模态模型自动复核；
- 翻译语义质量判断。

上述能力必须通过扩展接口加入，不能破坏已有 Schema 和规则检测链路。

## 4. 技术决策

| 领域 | 决策 |
| --- | --- |
| 语言 | Python 3.11 及以上，部署基线建议 Python 3.12 |
| 数据模型 | Pydantic v2 |
| PDF 引擎 | PyMuPDF |
| Office 归一化 | LibreOffice headless（server 层调用，core 零依赖；MPL 2.0） |
| 业务数据持久化 | SQLite（server 层内嵌；WAL、外键约束、版本化迁移） |
| 数值计算 | NumPy |
| 最优匹配 | SciPy `linear_sum_assignment` |
| 测试 | Python `unittest`，后续可迁移 pytest |
| 报告 | UTF-8 JSON |

PyMuPDF 同时承担 PDF 结构解析与页面渲染。业务模块不得泄漏 PyMuPDF 的 `Document`、`Page`、`Rect` 等运行时对象，只允许传递项目 Schema。

## 5. 许可证约束

PyMuPDF 开源版本使用 GNU AGPL v3。项目进入闭源分发、SaaS 或商业交付前，负责人必须完成以下任一事项：

1. 确认整个交付方式满足 AGPL v3；
2. 获取适用的 PyMuPDF 商业许可证；
3. 通过 Parser/Renderer 接口替换 PDF 引擎。

许可证结论必须记录在发布审批中，不能仅保存在口头沟通里。

LibreOffice 使用 MPL 2.0（许可友好，无 AGPL 传染），仅由 server 层作为系统级二进制调用，不随 core 发行包分发。

## 6. 核心数据契约

### 6.1 Page

- 页码从 `1` 开始；
- 页面尺寸使用 PDF point；
- 坐标原点位于左上角，X 向右、Y 向下；
- Block 和 Region ID 必须在当前页唯一；
- Region 引用的 Block 必须存在。

### 6.2 Block

- Block 是解析器产生的最小可比较元素；
- 文本默认细化到 Span；
- 原始解析器索引只能写入 `metadata`；
- 不允许在 metadata 中保存图片二进制或 PyMuPDF 对象。

### 6.3 Region

- Region 是匹配和检测的基本单元；
- Region 的 BBox 必须覆盖其全部子 Block；
- `children` 只保存 Block ID；
- 邻接关系只保存 Region ID。

### 6.4 Issue

- 所有检测器必须输出统一 Issue；
- Issue 必须包含页码、类型、严重度和可读描述；
- 能定位时必须提供 Target BBox；
- 阈值判断所使用的数值必须写入 `metrics`。

## 7. 组件边界

```text
Parser → Page/Block
Grouper → Page/Region
PageAligner → PageAlignment
Matcher → RegionMatch/StructuredDiff
Detector → Issue
Scorer → Score/Status
Reporter → QAReport/JSON
```

界面化分层（2025-08 增补；2025-08 二次拆分为双发行包）：

```text
frontend/（React+Vite+TS 前端）
  router/（TanStack Router：URL、一级菜单、直接访问与前进后退）
  services/（HTTP 协议、业务服务、TanStack Query 缓存键与失效）
  ↓ HTTP /api
server/src/document_qa_server/api/（FastAPI 协议层：DTO、状态码映射、静态挂载）
  ↓
server/src/document_qa_server/services/（应用服务：任务互斥、产物目录、用例编排）
  ↓
server/src/document_qa_server/persistence/（SQLite Schema、迁移、Repository）
  ↓
core/src/document_qa（核心引擎：pipeline/matching/detectors/scoring，不感知 HTTP）
```

- 仓库按发行包拆分：`core/`（document-qa，含 CLI，零 HTTP 依赖）与 `server/`（document-qa-server，依赖 core）；
- core 可独立安装，作为库或 CLI 嵌入其他系统，禁止 import fastapi/uvicorn 或 server 包；
- API 层不 import 核心引擎模块，只调用 services；
- services 返回核心模型或纯数据，不感知 HTTP；
- persistence 只服务于 server，负责事务、外键、数据迁移与查询；core 禁止
  import persistence 或 sqlite3；
- API 的请求 DTO 与核心 schemas 分开演化，互不强制联动。
- frontend 组件禁止直接调用 `fetch`；HTTP 细节只能位于 `services/httpClient.ts`，
  业务请求必须经过业务服务和 TanStack Query。一级页面状态以 URL 路由为唯一来源，
  禁止再用独立的菜单 state 复制路由状态。
- Tailwind CSS 只负责布局、响应式和组合样式，必须使用 `tw:` 前缀并消费现有
  `--qa-*` Token；禁止启用 Preflight、复制设计 Token 或替代 Ant Design 复杂组件。

- Parser 不负责问题判定；
- Grouper 不访问源文档与目标文档的对应关系；
- Matcher 不生成最终状态；
- Detector 不直接扣减总分；
- Scorer 不重新计算几何指标；
- Reporter 不修改检测结果。

## 8. 默认判定规则

严重度为 `INFO / LOW / MEDIUM / HIGH / CRITICAL`。

- `PASS`：没有 High/Critical 且得分不低于 90；
- `REVIEW`：存在 High，或得分处于 75 至 90；
- `FAIL`：存在 Critical，或得分低于 75。

Critical 问题优先于平均分。规则阈值必须集中配置，禁止散落在 CLI 或报告代码中。

## 9. 输入安全约束

- 默认单文件最大 100 MiB；
- 默认单文档最大 500 页；
- core 解析器只接受 `.pdf`；server 层额外接受 `.docx/.doc/.pptx/.ppt/.xlsx/.xls/.odt/.odp`，经 LibreOffice 归一化为 PDF 后进入同一流水线；
- 解析失败必须转换为明确异常，不得静默跳过；
- 输入文件永远视为不可信；
- 生产环境应在隔离 Worker 中解析文档，并设置 CPU、内存和执行时间限制；
- 文件名不能直接用于拼接输出路径。

## 10. 注释与编码约定

- 公共类、公共函数和模块入口必须包含中文 Docstring；
- 匹配、坐标、阈值和状态覆盖等主要逻辑必须有中文注释；
- 注释解释设计目的或判断原因，不重复代码字面含义；
- 类型、函数、变量和公开 JSON 字段使用英文；
- 禁止全局自动格式化和无关重构。

## 11. 测试与验收

代码完成必须同时满足：

- Schema 校验测试通过；
- Region 分组与匹配测试通过；
- 每个检测器至少包含一个阳性和一个边界用例；
- 可从测试代码生成 Source/Target PDF 并完成端到端比较；
- JSON 报告可重新通过 `QAReport` Schema 校验；
- 不包含密钥、令牌、文档正文样本或生成产物；
- Python 编译检查通过。
- SQLite 必须开启外键约束；Schema 迁移可重复执行且不得重复导入数据；
- 数据库内每张业务表和每个字段必须在 `schema_descriptions` 数据字典中有
  中文用途说明；建表 SQL 同时保留中文注释；
- 对比记录与完整 `QAReport` 必须在同一事务提交，读取后仍可通过当前
  `QAReport` Schema 校验；

## 12. 变更规则

- 新增 Issue 类型属于兼容变更；
- 删除或重命名公开字段属于破坏性变更；
- 匹配权重和严重度阈值变更必须附带 Golden Sample 结果；
- 更换 PDF 引擎必须保持 Schema 和坐标规范不变；
- 引入 OCR、Embedding 或多模态 API 时必须增加可关闭的适配层，并在测试中 Mock 外部认证 API。
- SQLite Schema 变更必须新增单向版本迁移，禁止修改已发布迁移；迁移必须
  幂等并保留可审计记录，不得静默丢弃旧 JSON 数据。
