# 需求待办：技术采纳方案（T1–T12）

> 来源：2025-08 架构对标梳理（T1–T5）与多格式/像素层讨论（T9–T10）。
> 每项含目标、方案、验收。通用约束：遵循 docs/project-contract.md；
> core 不引入 HTTP/服务依赖；完成后按 AGENTS.md 规则 6 验收
> （compileall + 分阶段验证 + 不变式推演）。

## 技术就绪度状态索引

| 编号 | 事项 | 状态 | 优先级 | 预估 |
| --- | --- | --- | --- | --- |
| T1 | 服务配置集中化（pydantic-settings） | ✅ 已落地 | P1 | 0.5 天 |
| T2 | 验收报告导出（XLSX + HTML） | ✅ 已落地（CLI + API/前端按钮） | P1 | 1–2 天 |
| T3 | 比较任务异步化 + 降级开关 | ✅ 已落地 | P2 | 1 天 |
| T4 | Docker Compose 交付 | ⭕ 待办 | P2 | 0.5 天 |
| T5 | 技术就绪度全景表 | ✅ 本文档持续维护 | — | 持续维护 |
| T9 | 多格式支持（LibreOffice 归一化 → PDF 流水线） | ✅ 已落地（docx 验证；pptx/xlsx 待真实样例回归） | P1 | 3–5 天 |
| T10 | 像素层检测（共享 T9 渲染设施） | ⭕ 待办（前置：复核闭环盲区量化） | P2 | 2–3 天 + 评估期 |
| T11 | MCP 服务（能力对外输出） | ✅ 已落地 | P1 | 1 天 |
| T12 | SQLite 业务数据统一持久化 + 样本管理 | 🟡 实施中 | P1 | 3–5 天 |

### 落地记录

- **T1（2025-08）**：`server/src/document_qa_server/settings.py`（DQA_ 前缀 + .env）；
  验证：默认行为不变 ✅、`DQA_PORT=9000` 覆盖生效 ✅、app 工厂默认构造 ✅、`.env.example` 已提交。
- **T2（2025-08）**：`core/src/document_qa/reporting/xlsx_reporter.py` + `html_reporter.py`
  + `templates/report.html.j2`；CLI `--export-xlsx/--export-html`。验证：真实样例
  119 条 Issue 与 XLSX 行数一致 ✅、HTML 含总览/逐页 ✅。
- **T2 补全（2025-08）**：`POST /api/report/export`（按对比记录导出，FileResponse
  下载流）+ 报告总览页「导出 XLSX / 导出 HTML」按钮。验证：真实样例 XLSX 119 行
  与报告一致 ✅、HTML 28KB 渲染正常 ✅、404 路径 ✅。注意：导出锚点是
  history_record_id，历史回看前的会话内报告无锚点（按钮禁用）。
- **T3（2025-08）**：CompareService 任务注册表（queued/running/done/error +
  history_record_id 回传）；`POST /api/compare` 异步默认返回 task_id，
  `GET /api/tasks/{id}` 轮询；`DQA_ASYNC_MODE=false` 完整同步回归路径。
  前端提交后 1s 轮询。验证：异步 8s 完成、报告 86.80 与同步一致 ✅、
  同步开关回归 ✅、39 项测试全绿 ✅。遗留：任务注册表无 TTL 清理
  （进程内字典，重启即清）——已由下文 L-1 补上终态 1h TTL。
- **T9（2025-08）**：`server/src/document_qa_server/services/normalization_service.py`
  （LibreOffice headless，隔离 profile 绝对路径 URL，产物摘要缓存，60s 超时）；
  CompareService 归一化接入 + `conversion_noise_ratio` 阈值叠加（Profile 副本上改，
  core 检测零改动）；`QAReport.metadata.normalized_from` 兼容新增；
  `GET /api/normalize/status` 引擎探测。验证：docx 对真实样例全链路
  `pass 100.00` ✅、缓存复用 ✅、非法格式拒 ✅、PDF 原路径基线 86.80 不变 ✅、
  39 项测试全绿 ✅。遗留：pptx/xlsx 真实样例回归、soffice 缺失 503 路径的
  集成验证（服务已映射，未跑容器场景）。
- **T6 术语库（2025-08）**：core `glossary.py`（版本化 Glossary/GlossaryEntry，
  源术语唯一性校验，内置示例）+ `detectors/glossary.py`（正向检查：源区域
  出现术语 → 目标区域须命中任一允许译法；大小写可配；Issue 带
  glossary_reference 可追溯）；`GLOSSARY_VIOLATION` 枚举 + 扣分上限 12。
  Pipeline 可选注入（缺省不启用，行为不变）。server `GlossaryService`
  （CRUD + 按引用加载，路径安全）+ `/api/glossary/*` 路由；CompareRequest
  增 `glossary_reference`。前端：侧边栏「术语库」管理页（条目可编辑表格/
  保存/删除/复制）+ 比较栏术语库下拉。验证：保存/列表/读取 ✅、带术语库
  比较 14 条术语违规（84.11）vs 无术语库 86.80 ✅、非法引用 400 ✅、
  46 项测试全绿（新增 7 项）✅。
- **T11 MCP 服务（2025-08）**：`server/src/document_qa_server/mcp_server.py`
  （FastMCP stdio，12 工具：compare/history/report/export/verify/profile×3/
  glossary×3/engine_status）；直接复用 services 层（不经 HTTP），历史记录与
  Web 互通；LLM 输出裁剪（摘要 + 按页取数 + 导出只回路径）。入口
  `document-qa-mcp`（pyproject extra `[mcp]`，mcp>=1.17,<2——2.0 API 重命名
  且生态未跟上，锁定 1.x）。验证：MCP 客户端 stdio 协议级冒烟——12 工具
  列举 ✅、真实比较 86.80/119 摘要 top10 ✅、单页报告 ✅、XLSX 导出 ✅。
  客户端配置示例见 docs/manuals/mcp-server.md（Claude Desktop/Cursor/通用）。

## T12 SQLite 业务数据统一持久化 + 样本管理

**问题**：样本、对比历史、完整报告、规则配置、术语库和人工复核分别依赖
目录 JSON 与进程/文件锁。新增可编辑样本对后，唯一性、关联完整性、并发
写入、版本追溯和备份会继续复杂化；现有 `.json` + `.summary.json` 还存在
双文件一致性负担。

**方案**：

1. server 新增 SQLite persistence 层，数据库位于
   `webapp-artifacts/metadata.sqlite3`；开启 WAL、外键与 busy timeout，使用
   版本化、幂等迁移，不向 core 引入数据库依赖。
2. 建立文件元数据、样本对、规则版本、术语库版本、对比记录、完整报告、
   人工复核和迁移记录等关系表；完整 `QAReport` 以 JSON 正文入库，同时把
   分数、状态、页数、问题数等列表字段独立建列。
3. SQLite 无原生 `COMMENT ON`，因此建表 SQL写中文注释，并建立
   `schema_descriptions` 数据字典，逐表逐字段保存中文用途说明。
4. 原始 PDF/Office、渲染图和导出文件仍在文件系统；数据库保存内容摘要、
   安全路径及关联。样本删除只归档元数据，不连带删除历史引用文件。
5. 启动时幂等导入现有 history/profile/glossary/review JSON；原文件保留作为
   回退证据。API 外部字段保持兼容，内部服务切换为 Repository。
6. 前端新增「样本管理」：创建源/目标文档对、维护 BCP 47 语言对、列表、
   编辑说明、归档及一键载入工作台；内置样本只读。

**验收**：

- `PRAGMA foreign_key_check` 无错误，所有业务表及字段均能从数据字典查询中文说明；
- 重复启动迁移不重复导入；现有历史、配置、术语库和复核数据数量不减少；
- 比较完成后记录与完整报告原子入库，报告可通过 `QAReport` 校验并正常导出；
- 样本创建、更新、归档、载入工作台闭环通过，内置样本禁止修改和归档；
- Python 编译、前端构建及真实 PDF 分阶段验证通过。

### 对抗性审查与修复（2025-08）

双路对抗审查（人工对抗用例 + 双子代理代码审查）发现并修复以下缺陷，
回归测试固化在 `tests/test_adversarial_regressions.py`（10 项）：

| 编号 | 严重度 | 缺陷 | 修复 |
| --- | --- | --- | --- |
| #1 | 高 | 数字正则把 `1,137.5` 切成两 token；前导零/全角数字不等价 | 组合正则 + 归一化（core/content.py） |
| #2 | 高 | 混排源页（mixed）被判拉丁 → 整页漏译假阳性（实测 4/4 区域误报） | mixed 源跳过漏译检测 |
| #3 | 高 | 术语子串无词边界：AI 命中 said/raining（实测全链路误报） | 拉丁术语 `\b` 词边界，CJK 保持子串 |
| #4 | 高 | history record_id 锁外生成，同毫秒并发碰撞静默丢记录（实测 20 写剩 1） | 锁内生成 + 微秒 + 随机后缀 |
| H-1 | 高 | CORS `*` + 任意路径输入 = 浏览器跨源读本机文档 | 默认 origin 收紧为本地前端 |
| H-2 | 高 | 上传整读内存后才校验大小 → OOM | 流式分块 + 累计超限中止 |
| M-1 | 中 | execute 只捕两类异常，磁盘满等错误任务卡 running | `except Exception` 兜底置 error |
| M-3 | 中 | soffice 硬编码，仅有 libreoffice 命令的系统崩溃 | 与 check_engine 同源解析二进制 |
| M-4 | 中 | 双重 stem：report.v2.docx 找 report.pdf 误报失败 | 产物名 = 源完整主名 + .pdf |
| M-5/M-6 | 中 | 失败路径 staging 残留；同 digest 并发 staging 竞争 | finally 统一清理 + staging 随机后缀 |
| #5 | 中 | TABLE/CHART 组 max() 空序列崩溃（grouper） | 非 TEXT/IMAGE 组透传类型建 Region |
| #6 | 低 | 同页同术语多区域 Issue ID 重复 | ID 加目标区域段 |

遗留项二轮修复（同日全部处理）：

- **M-2**：渲染目录按任务隔离（`pages/task-<id>/source|target/`），
  索引移入 `_run_lock` 内生成（返回相对 pages/ 根的完整路径段）；
  前端 `pageImage` 按后缀匹配新路径。验证：新任务索引 200、旧共享
  路径 404、连续两任务目录互不串染 ✅。
- **M-7**：history 目录级文件锁（fcntl.flock，Windows 回退线程锁），
  `get` 容忍并发淘汰。验证：4 进程 ×15 写 **60/60 无丢失** ✅。
- **L-1**：任务注册表 TTL（终态 1h 清理，结果已持久化 history）。
- **L-2**：ReviewService 锁字典超万次创建时回收未持有锁。
- J 组评分宽松维持原状（封顶为设计本意，待产品确认）。
  验证：56 项测试全绿、Golden 基线 86.80 不变、并发/边界对抗
  用例全部转阴。

---

## T1 服务配置集中化（pydantic-settings）

**问题**：端口、artifacts 目录、样例目录、上传上限等散在
`server/src/document_qa_server/api/app.py` 与各服务构造参数中，
改配置要改代码，环境间切换（开发/私有化部署）无机制。

**方案**：

1. 新增 `server/src/document_qa_server/settings.py`：
   - `ServerSettings(BaseSettings)`：`host`、`port`、`artifacts_dir`、
     `samples_dir`、`max_upload_bytes`、`cors_origins`；
   - 全部带默认值（当前行为不变），`.env` 与环境变量可覆盖；
   `model_config = SettingsConfigDict(env_prefix="DQA_")`。
2. `create_app()` 改为读取 settings，服务实例构造参数全部来自 settings。
3. `__main__.py` 读取 `settings.host/port` 作为 argparse 默认值。
4. `.env.example` 提交到仓库根，`.gitignore` 已含 `.env`。

**依赖变更**：`server/pyproject.toml` 增加
`pydantic-settings>=2.3,<3`（部署分组或核心均可，建议核心——配置是刚需）。

**验收**：

- 无 `.env` 时行为与当前完全一致（端口 8765、产物目录不变）；
- `DQA_PORT=9000 .venv/bin/document-qa-server` 实际监听 9000；
- API 全链路冒烟（health/upload/compare）通过。

---

## T2 验收报告导出（XLSX + HTML）

**问题**：验收签核需要给人看的交付物；JSON 报告对项目经理/客户不可用。
对应路线图 #8。

**方案**：

1. 归属 **core**（报告生成是引擎能力，CLI 也要用），新增
   `core/src/document_qa/reporting/xlsx_reporter.py` 与
   `html_reporter.py`，与 JSONReporter 并列。
2. XLSX（openpyxl）：
   - Sheet1 问题清单：页码/类型/严重度/描述/源目标区域/坐标/判定（预留
     复核结论列，供 T6 复核数据回填）；
   - Sheet2 文档摘要：状态/分数/页面分布/Profile 引用。
3. HTML（Jinja2 内置模板，单文件内联 CSS，可直接邮件发送）：
   - 总览统计 + 逐页问题表 + 需复核页的内嵌 PNG（相对路径引用渲染产物）。
4. CLI 增加 `--export-xlsx PATH`、`--export-html PATH`；
   server 增加 `POST /api/report/export`（入参 task 摘要 + 格式，返回文件）。
5. 模板放 `core/src/document_qa/reporting/templates/`，随 wheel 打包
   （hatch 配置 package-data）。

**依赖变更**：`core/pyproject.toml` 增加 `openpyxl>=3.1,<4`、`jinja2>=3.1,<4`。

**验收**：

- 真实样例导出的 XLSX 能在 Excel/WPS 打开，问题行数与 JSON 报告一致；
- HTML 单文件浏览器打开正常、图片显示、严重度配色正确；
- Golden Sample 断言扩展：导出产物的问题总数 = 报告 issue 总数。

---

## T3 比较任务异步化 + 降级开关

**问题**：compare 全程持有 `_run_lock`，第二个请求要等第一个完整跑完
（含渲染），批量场景串行阻塞；前端无进度反馈。

**方案**（学对标项目的"降级开关"思想，但**不引入 Redis/Celery**）：

1. `CompareService` 增加任务注册表：
   `dict[task_id, TaskState]`（status: queued/running/done/error + 结果引用），
   保留现有互斥锁做单 worker 语义。
2. API 拆分：`POST /api/compare` → 立即返回 `task_id`；
   `GET /api/tasks/{task_id}` → 轮询状态与结果。
3. 执行层用 FastAPI `BackgroundTasks`（settings 加开关
   `async_mode: bool = True`；False 时退回同步行为，CLI/测试零影响）。
4. 前端 run-bar 改为提交后轮询，进度态显示"排队/比较中/渲染中"。
5. 任务注册表带 TTL 清理（done 状态保留 1 小时）。

**明确不做**：Celery/Redis（对齐当前单机单用户定位）；并发多 worker
（渲染目录仍单写者）。若未来需要，T1 的 settings 开关留了切换位。

**验收**：

- 同步开关关闭时 API 行为与现在完全一致（回归保护）；
- 异步模式下连续提交两个任务，第二个返回 queued，第一个完成后自动执行；
- 前端轮询到结果后各视图正常渲染。

---

## T4 Docker Compose 交付

**问题**：私有化交付需要"一条命令起服务"；当前依赖本机 venv + 手动起
两个进程。

**方案**：

1. 仓库根新增 `deploy/Dockerfile`：
   - 多阶段构建：builder 阶段 `pip install core/ server/` + frontend 产物
     （`bun run build` 或在容器内 node 构建）；
   - 运行阶段仅含 venv + frontend/dist，uvicorn 托管 API 与静态前端
     （FastAPI `StaticFiles` 挂载 `/`）。
2. `deploy/docker-compose.yml`：单服务，卷挂载
     `./webapp-artifacts`（产物持久化）与 `./examples`（样例，只读）。
3. 环境变量透传 T1 的 `DQA_*` 前缀。
4. `AGENTS.md` 常用命令补 compose 起停命令。

**注意**：PyMuPDF AGPL（契约 §5）——私有化镜像分发前过一遍许可证结论，
写进部署 README。

**验收**：

- `docker compose up` 后 `http://localhost:8765` 同时可用（API + 前端）；
- 上传→比较→逐页详情全链路在容器内通过；
- 产物目录在容器重启后保留。

---

## T5 技术就绪度全景表（本文档）

**做法**：本文档的索引表即首版；后续每次能力落地或新增规划时同步更新
状态列（✅ 已落地 / 🟡 桩或部分 / ⭕ 规划），新增事项按 T+N 编号追加。

**维护纪律**：

- 新增待办必须写清：问题、方案、验收三段，不许只留一行标题；
- 状态只能由实现者在本体完成后修改，且需附验证证据（命令 + 结果）。

---

## T9 多格式支持（LibreOffice 归一化 → PDF 流水线）

**问题**：验收场景要求支持 Word / PPT / Excel / 图片的校验；当前引擎
仅接受 PDF（契约 §3.2 明确排除）。若按"每种格式一套原生解析器"
（python-docx/python-pptx/…）的路线扩展，将产生 N 条平行链路，
匹配/检测/评分逻辑无法复用，维护面随格式数线性增长。

**方案**（归一化前置，而非 N 条解析链）：

1. **统一转换层**：LibreOffice headless（`soffice --convert-to pdf`）
   把 docx/doc、pptx/ppt、xlsx/xls 统一转成 PDF；转换产物落
   `webapp-artifacts/normalized/`，后续完全走现有 PDF 流水线
   （parse → group → align → match → detect → score）。
   core 引擎**零改动**。
2. **接入位置**：server 层新增 `NormalizationService`（转换编排、
   格式探测、超时与并发控制）；core 的 Parser 接口保持 PDF-only，
   保证 core 发行包不背 LibreOffice 运行时依赖。
3. **格式探测**：扩展名 + 魔数双重校验（对齐 FileService 现有做法），
   支持 `.docx .doc .pptx .ppt .xlsx .xls .odt .odp`；图片类
   （png/jpg）单独评估——无文本层，需 T10 像素层先行，暂列二期。
4. **转换噪声容忍**：LibreOffice 渲染与 Office 原生排版存在 1–3%
   版面偏差。处理方式：① Profile `alignment` 节新增
   `conversion_noise_ratio`（默认 0.03），偏移类检测阈值自动叠加
   该容差；② 报告 metadata 记录 `normalized_from: <原格式>`，
   提示验收人结论含转换因素。
5. **契约修订**：§3.2 把"DOCX/PPTX 原生解析"排除项改为
   "多格式经 LibreOffice 归一化支持，原生结构解析仍排除"；
   §4 技术决策表补 LibreOffice 条目（MPL 2.0，许可友好）。
6. **依赖形态**：LibreOffice 是系统级二进制（非 pip 依赖），运行时
   探测不可用时返回明确错误 + 安装指引；T4 的 Docker 镜像内置。

**验收**：

- 准备 docx/pptx/xlsx 真实样例各一对（原文 + 译文），全链路
  分阶段验证跑通，报告含 `normalized_from` 标记；
- 同一 PDF 直传 vs 归一化路径（PDF→PDF 恒等转换）结果一致，
  证明转换层无副作用；
- `soffice` 不存在时 API 返回带安装指引的 503，而非堆栈；
- 转换超时（默认 60s/文件）可配置并有超时路径测试。

---

## T10 像素层检测（共享 T9 渲染设施）

**问题**：纯文本层链路存在三类盲区——视觉属性丢失（颜色变浅/图片
替换）、重叠遮盖的视觉后果（BBox 相交≠视觉不可读）、非文本元素
（水印/线条/形状）。对标的"两重处理"（文本层+像素层）正是为此，
但其像素层为空目录；我们的机翻对照场景盲区出现率未量化。

**前置条件**（重要——先量化再投入）：

- 利用现有复核闭环数据：统计真实样例中"人工判定为确认问题、
  但文本层检测器未报"的 Issue 占比；
- 占比 < 5% 时本项降级为 P3 观望；≥ 5% 才启动实施。

**方案**：

1. **复用而非新建**：渲染用现有 PyMuPDF Renderer（T9 之后多格式
   也有 LibreOffice 渲染兜底）；不引入 LibreOffice+Poppler 双渲染。
2. **检测器**：core 新增 `detectors/pixel.py`，OpenCV-headless 实现：
   - **页面级结构差分**：源/目标同页渲染图 SSIM 或直方图差分，
     差异区聚类成伪 Region，走现有 Issue 通道（`severity: MEDIUM`
     起步，类型复用 `OTHER`，稳定后再立 `PIXEL_DIFF` 新类型）；
   - **DPI 对齐**：强制统一渲染 DPI（当前 144），页面尺寸不一致
     时先缩放归一；抗锯齿噪声用形态学开闭预处理吸收。
3. **集成方式**：作为可选检测器挂进 pipeline（Profile toggles 加
   `pixel_diff`，默认 **关闭**——避免噪声影响既有 Golden 基线，
   启用需显式配置），与 T9 的转换噪声容差共享阈值体系。
4. **依赖变更**：core 增加 `opencv-python-headless>=4.9`（可选
   extra `pixel`，未安装时检测器自动禁用并 INFO 提示，不强依赖）。

**验收**：

- 人工构造 3 类盲区样例（改颜色/换图/加水印）各一，检测器全部命中；
- Golden Sample 默认配置下行为零变化（pixel_diff 默认关）；
- 启用后真实样例的误报率经复核闭环标注 < 30% 才可转默认开启评估。

---

## 历史路线图对照

原「验收场景缺口清单」（2025-08 讨论沉淀）与本文档编号映射：

| 原编号 | 事项 | 现状 |
| --- | --- | --- |
| #1 漏译检测 | ✅ 已落地（content 检测器） |
| #2 数字一致性 | ✅ 已落地 |
| #3 术语表 | ✅ 已落地（T6） |
| #4 表格结构检测 | ⭕ 待办（候选 T7） |
| #5 文本流检测 | ⭕ 待办（候选 T8） |
| #9 多格式支持 | 本文档 T9（P1） |
| #10 像素层检测 | 本文档 T10（P2，先量化盲区） |
| #6 复核闭环 | ✅ 已落地（判定持久化 + UI） |
| #7 批量任务 | ⭕ 待办（T3 异步化是其前置） |
| #8 报告导出 | 本文档 T2 |
