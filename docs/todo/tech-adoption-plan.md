# 需求待办：技术采纳方案（T1–T24）

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
| T10 | 像素层与图像文字检测 | 🟡 P1/P2 已落地；OCR 误报评估与 P3 待办 | P1 | 评估期 |
| T11 | MCP 服务（能力对外输出） | ✅ 已落地 | P1 | 1 天 |
| T12 | SQLite 业务数据统一持久化 + 样本管理 | 🟡 实施中 | P1 | 3–5 天 |
| T13 | 前端 UI 契约与页面组件基线 | 🟡 实施中（质检记录契约化完成） | P1 | 2–3 天 |
| T14 | 前端路由与服务端状态统一 | ✅ 已落地 | P1 | 1–2 天 |
| T15 | Tailwind CSS v4 受约束接入 | ✅ 已落地（未批量迁移页面） | P2 | 0.5 天 |
| T16 | M↔N 逻辑文本分组匹配 | ✅ 已落地 | P1 | 1 天 |
| T17 | 跨行样式与条目边界安全分组 | ✅ 已落地 | P1 | 0.5 天 |
| T18 | 文本重叠双轴判定与双语证据 | ✅ 已落地 | P1 | 0.5 天 |
| T19 | 问题编号多条件过滤 | ✅ 已落地 | P2 | 0.25 天 |
| T20 | 服务端持久化日志（按天轮转 + request_id 关联） | ✅ 已落地 | P1 | 0.5 天 |
| T21 | 复核反馈自学习回路（误报归因 → AI 修复报告 / 规则调优 → 定期闭环） | 🟡 P0+P1+AI 修复报告已落地；P2 待办 | P2 | P2 1–2 天 |
| T22 | Python 工程治理与可复现构建 | 🟡 实施中 | P0 | 1–2 天 |
| T23 | 比较任务子进程隔离（OCR 不再拖慢 API） | ✅ 已落地 | P0 | 0.5–1 天 |
| T24 | 多机部署时的任务队列选型（Celery 评估） | ⭕ 待办（触发条件制） | P3 | 触发后评估 |
| T25 | 评审修复第一批：越界容差 / 移页数字豁免 / 事务外哈希 / review_task_id 下发 | ✅ 已落地（2026-08） | P0 | 0.5–1 天 |
| T26 | 评审修复第二批：字号基线加权 / language_overrides 贯通 / 脚本表统一 / 解析器合规（匹配惩罚经 Golden 否决） | ✅ 已落地（2026-08，②待方案重定） | P0 | 1–2 天 |
| T27 | M→1 合并区域 span 级字号对照（修复图表标题合并排版漏报） | ✅ 已落地（2026-08） | P1 | 0.5–1 天 |
| T28 | 矢量图形元素对比（椭圆/色块/线条缺失与样式变更，候选） | ⭕ 待办（2026-08 排查发现的范围缺口） | P3 | 评估后定 |
| T29 | invisible_text 误报修复（dark_box 面积预过滤过严） | ✅ 已落地（2026-08） | P0 | 0.5 天 |
| T30 | 数量归一补全：英文缩写金额（$100M/$4.99B）与裸英文月份（in January） | ✅ 已落地（2026-09） | P1 | 0.5 天 |
| T31 | 竖排/逐字 span 文本的区域级可读性（UN 类文档数字/月份在区域内不连续） | ⭕ 待办（2026-09 排查发现的解析层局限） | P3 | 评估后定 |
| T32 | 碎片检测对混合脚本/拉丁完整短标签的保守误报（A轮/NDA/II期） | ✅ 已落地（2026-09，源页面词形比对豁免） | P3 | 0.5 天 |
| T33 | 横排单行长标题的 region_resized 宽度误报（text_label_max_chars 上限外的标题类单行文本） | ⭕ 待办（2026-09 排查发现的同族误报） | P3 | 评估后定 |
| T34 | 数量归一补全二：英文基数词混排区间（six to 12）与中文纯乘数链单位声明（百万美元） | ✅ 已落地（2026-09） | P1 | 0.5 天 |
| T35 | 文本方向元数据沉淀与消费（line dir/wmode 入 Block metadata；消费端随 T31/T33 搭车或按触发条件立项） | ⭕ 待办（2026-09 评估：直接 ROI 低、基建价值中等） | P3 | 两阶段合计 0.5–1 天 |
| T36 | 匹配内容感知：数量签名否决 + 分配留空语义（图表轴标签错配连锁，20260901-093939） | ⭕ 待办（2026-09 两组实验已完成，方案需 Golden 校准与确认） | P2 | 1–2 天 |

---

## T29 invisible_text 误报修复（dark_box 面积预过滤过严）

**问题**：AI 排查任务书（记录 `20260831-104238-224-3e54`，#6/#7/#8）：
第 1 页饼图白字百分比标签（"1% 12%"、"30% 15%"、"16% 26%"）被 invisible_text
判为高危，但渲染像素采样显示标签背衬为深蓝 (0,41,87) / 橙 (243,111,33)
——白字完全可见，属误报。根因：`_page_background` 的
`dark_box_min_area_ratio=0.1`（页面积 10% ≈ A4 上 4.8 万 pt²）把饼图
扇形矢量填充（345~1989 pt²）全部当作"装饰小色块"过滤出
`dark_boxes`，`_overlaps_dark_block` 无从豁免。该误报自该文档对首次
质检即存在（旧记录 095940 第 1 页同类 14 条），非回归。

**方案**：`dark_box_min_area_ratio` 默认 0.1 → **0.0005**（A4 上约
242 pt²，相当于 3~4 个字符墨迹的噪声下限）。语义调整：面积预过滤只
负责排除发丝级噪声，"色块是否构成文字背衬"交由
`_overlaps_dark_block` 的 30% 重叠判定——有色块背衬即设计意图
（豁免），背景图形丢失（色块随之消失）时仍正常检出，不构成漏报
路径。全部取值集中于 RuleProfile。

**验收与落地记录（2026-08）**：

- SyneosHealth 文档对：13 条 p1 invisible 误报全部消失（含任务书
  3 条），零新增，212 → 199 条、48.14 → 51.71 分；
- 构造用例：彩底白字（有背衬）不报；背景块丢失的白字仍检出 HIGH；
- Golden（un-china 对）：275 → 237 条，消失的 38 条全部为
  invisible_text，其他类型零扰动、零新增；**38 条逐一渲染像素核验，
  背衬最深通道均 < 200（存在彩色/深色背衬），豁免全部合理，无误豁免**；
- `uv lock --check`、Ruff、渐进 mypy、compileall、双包构建通过。

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
- **T13 第一阶段（2026-08）**：新增 `frontend/docs/design/ui-guidelines.md` 与六个页面基础组件，
  「质检记录」已迁移为参考页。验证：前端构建 ✅、Python compileall ✅、搜索
  9/28 与状态筛选 13/28 ✅、详情抽屉与工作台回跳 ✅、800 px 窄屏页头/工具栏
  自动纵排 ✅、浏览器控制台 0 错误 ✅。静态检查仅保留既有 `PageDetails.tsx`
  Fast Refresh 警告；其余管理页面尚未迁移，因此 T13 继续保持实施中。
- **T13 契约补强（2026-08）**：依据 1440 × 1024 企业文档管理参考图，将原
  指导性规范升级为可量化 UI 契约，明确 72 px 顶栏、260/256 px 双侧栏、
  36 px 控件、40 px 菜单项、表格字号与内边距、4/8/12 px 圆角体系，
  并补充 375–1440 px 响应式、可访问性、Ant Design Token 映射和 ±2 px 验收容差。
- **T13 第二视觉参考（2026-08）**：第二张 1440 × 1026 图片仅用于补充紧凑
  卡片、筛选区和尾部控件的视觉尺度。契约明确禁止由参考图推导页面结构、分类、
  字段、启停、更多菜单等功能；当前系统先按真实业务任务确定组件，再应用对应的
  字号、间距、圆角和密度规范。
- **T13 质检记录契约化（2026-08）**：保留搜索、状态筛选、刷新、详情、工作台
  回跳和重新质检能力，仅调整视觉骨架。实测 1440 px 下页头 72 px、工具栏
  68 px、控件 36 px、容器圆角 8 px；数据单元格不设置固定高度，使用 14/22 px
  与 Ant Design Table 默认密度自然形成，表头完整使用组件默认样式。1024/768/375 px
  无页面级横向溢出。搜索 9/28、
  叠加状态筛选 5/28、
  详情抽屉和工作台回跳通过，浏览器控制台 0 错误。后续校正：应用基础字号在
  Ant Design Token 与 `body` 显式锁定为 14 px，时间列恢复 14 / 22 px；表头移除
  页面级字号、行高、字重、颜色、背景和内边距覆盖，完整使用 Ant Design Table 默认样式。
- **T13 契约 1.4 校正（2026-08）**：明确 Ant Design 默认样式的版本与密度边界，
  批量选择改为条件规则，并增加移动端单元格 8 px 例外。新增满足 4.5:1 的状态
  文字色和次要文字色，保留原强调色用于圆点与浅底；全局补齐控件、圆角、字号、
  线宽和动效 Token。应用外壳实测 375 px 使用移动顶栏与抽屉，768/1024 px
  使用 72 px 图标栏，1280/1440 px 使用 260 px 侧栏，五档均无页面级横向溢出。
  质检记录补齐筛选空状态操作和包含处理建议的错误反馈。
- **T16（2026-08）**：新增双侧几何对应图与 M↔N 逻辑文本流组合，逻辑组
  配对锁定且证据保留原子 Region ID。记录 `20260825-045913-285-eb41` 对应
  样例完成六阶段验证：166/206 Blocks、107/182 原子 Regions、1 页配对、
  105 对逻辑匹配、131 Issues、报告 10.00；问题 83 与同因 resize 误报消失，
  高等级问题由 81 降至 76；`compileall` 与 diff 检查通过。
- **T17（2026-08）**：同一原始 PDF Block 改为先按跨行颜色、字号、字重、
  斜体及列表条目建立硬边界，再做空间连通；同 Block 拆分组件不互判字形框
  重叠，局部等量组件按阅读顺序锁定。记录 `20260825-093918-816-2b9e`
  对应样例完成六阶段验证：112/193 Regions、110 对匹配、130 Issues；#84
  resize 误报消失，高等级保持 76，报告 10.00；`compileall` 与 diff 检查通过。
- **T18（2026-08）**：文本重叠增加面积与双轴侵入联合判定，并在 Issue 中
  保存两组匹配原文、译文及 BBox；详情页按四行证据成对展示。记录
  `20260825-111352-271-707f` 对应样例复验后 #130 消失，Issues 130→128、
  High 76→74，剩余 8 条文本重叠均含双侧证据；前端 build/lint、Python
  compileall、QAReport 校验与 diff 检查通过。
- **T19（2026-08）**：工作台问题编号过滤支持英文逗号、中文逗号和空白分隔，
  每个编号条件保留模糊匹配并按 OR 合并结果；`#` 前缀和重复条件可自动规范化。
  实测 `84,128` 与 `84， #128` 均同时显示 #84/#128，控制台 0 错误，前端
  build/lint 与 diff 检查通过。

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

## T13 前端 UI 契约与页面组件基线

**问题**：现有页面虽然使用 Ant Design，但页面标题、内容区块、列表密度、
状态标签、空状态和操作入口由各页面分别实现，存在内联颜色、重复布局和文案
不一致。新增页面继续复制局部做法会扩大视觉与交互差异，也增加后续改版成本。

**方案**：

1. 新增 `frontend/docs/design/ui-guidelines.md` 作为可验收 UI 契约，量化色彩、字体、间距、
   圆角、页面结构、表格、状态、表单、响应式规则及允许误差。
2. 色彩语义继续以 `frontend/src/uiTokens.ts` 为 TypeScript 唯一来源；布局节奏
   统一为 `frontend/src/global.css` 的 `--qa-*` CSS 变量，业务页面禁止新增裸色值。
3. 建立 `PageHeader`、`PageSection`、`DataTable`、`StatusTag`、`EmptyState`、
   `FormDrawer` 基础组件，列表型页面通过组合基础组件完成，不重复实现外壳。
4. 先将「质检记录」迁移为参考实现，补齐页面说明、刷新、文档搜索、状态筛选、
   标准操作按钮和双场景空状态；再逐步迁移样本管理、规则管理和术语库。
5. 工作台报告详情属于高密度专用工作流，可保留专用组件，但必须复用全局色板、
   状态语义和基础布局变量。

**验收**：

- 「质检记录」仅通过公共页面组件组织主体，搜索、状态筛选、刷新、分页、空状态
  与详情/重跑入口均可用；用户可见文案统一使用“质检”；
- 页面代码不自行映射状态颜色，不用文本分隔符模拟操作按钮；
- `frontend` 构建与静态检查通过，桌面及窄屏下页头、工具栏和表格可用；
- 浏览器验证侧栏导航、质检记录筛选、详情抽屉与工作台回跳无控制台错误；
- 样本管理、规则管理和术语库完成迁移前，本项保持“实施中”，不得标记为已落地。

## T14 前端路由与服务端状态统一

**问题**：一级菜单由 `App` 本地 state 控制，刷新、直接访问和浏览器前进后退不能
恢复页面；请求散落在组件和 `api.ts`，存在裸 `fetch`、重复错误解析及缓存失效
规则缺失。

**方案**：引入 `@tanstack/react-router` 与 `@tanstack/react-query`。一级页面
映射为稳定 URL；HTTP 协议收敛到 `services/httpClient.ts`，DTO 与无状态业务服务
保留在 `api.ts`，Query API 门面统一查询键、请求去重、Mutation 和缓存失效。
组件不再直接调用 `fetch`。

**验收**：五个一级菜单拥有独立 URL，刷新及前进后退保持页面；源码裸 `fetch`
仅存在于 HTTP 客户端；比较、记录、样本、配置、术语、复核和导出请求均经过
TanStack Query；前端构建、静态检查和浏览器路由回归通过。

## T15 Tailwind CSS v4 受约束接入

**问题**：页面布局与响应式 CSS 仍需重复编写，但直接引入 Tailwind 默认主题和
Preflight 会形成第二套色板、间距、圆角和元素重置，与 UI 契约及 Ant Design 冲突。

**方案**：使用 Tailwind CSS v4 官方 Vite 插件，禁用 Preflight，并统一使用
`tw:` 前缀。通过 `@theme inline` 清除默认视觉主题，只映射现有 `--qa-*` 色彩、
间距、圆角、字号、断点和阴影 Token。Ant Design 继续负责复杂组件，现有页面不做
批量重写。

**验收**：构建产物包含 `tw:` 工具类和 `qa` Token 工具类，不包含 Preflight
全局重置；现有页面渲染、路由和表格行为不变；源码不新增 `tailwind.config.js`，
构建、静态检查和五档浏览器冒烟通过。

## T16 M↔N 逻辑文本分组匹配

**问题**：不同语言 PDF 会把同一视觉文本流解析为不同数量的 Region。原子级
1↔1 匹配会把一侧被拆分的标题或段落错配到远端文本，并把正常高度差判为
高等级 `region_resized`。

**方案**：保留 Grouper 原子 Region，在匹配前构建双侧几何对应图；仅当连通
分量两侧分别都是同类型、同栏、连续且样式相近的单一文本流时，组合为逻辑
Region。逻辑组共享内部配对键，禁止全局分配拆散已确认的 M↔N 对应关系；报告
证据保留两侧原子 Region ID。所有约束继续集中在 `RuleProfile`。

**验收**：真实记录 `20260825-045913-285-eb41` 对应样例完成 parse → group →
alignment → match → detect → report 分阶段验证；问题 83 及同因 resize 误报消失；
普通 1↔1、跨栏、非连续和超大连通分量不合并；`compileall` 与 diff 检查通过。

## T17 跨行样式与条目边界安全分组

**问题**：Grouper 仅按原始 PDF Block 和空间连通性合并 Span，会把颜色不同的
标题与正文、相邻列表项合成一个 Region，继而产生高等级尺寸误报。

**方案**：同行仍允许混合样式；跨行合并必须满足规范化颜色、容差内字号、字重
和斜体兼容，并在编号、项目符号和冒号明细行处切断文本流。相同原始 Block 的
拆分组件不互判字形框重叠；双侧等量局部组件按阅读顺序锁定。自然增加一行且
宽度、字号、每行高度稳定的翻译回流不判尺寸剧变。阈值统一进入 `RuleProfile`。

**验收**：记录 `20260825-093918-816-2b9e` 的 #84 不再产生 resize Issue；蓝色
标题与四个黑色正文条目独立成组并按顺序匹配；同行混合样式及同样式续行保持
合并；六阶段真实 PDF 验证、Profile 序列化、`compileall` 和 diff 检查通过。

## T18 文本重叠双轴判定与双语证据

**问题**：相邻文字行的字体 BBox 可能发生亚点级接触，单一面积比例会产生肉眼
不可见的重叠误报；Overlap Issue 只保存目标侧两个区域，详情无法展示原文依据。

**方案**：文本互叠同时要求交集面积、水平侵入和垂直侵入达标；文字图片重叠
保持既有拓扑逻辑。优先使用 RegionMatch 找到两组源侧对应区域，并把双方文本、
BBox 和 Region ID 写入 metrics；详情页以“原文区域 1/2、译文区域 1/2”展示。

**验收**：记录 `20260825-111352-271-707f` 的 #130 被排除；真实重叠继续保留，
每条文本重叠包含双轴比例和两组原文证据；旧报告缺少原文时仍可展示两组译文；
完整报告通过 Schema 校验，前端 build/lint、页面冒烟和 Python 编译通过。

## T19 问题编号多条件过滤

**问题**：工作台问题列表一次只能输入一个展示编号，复核多个分散问题时需要反复
修改过滤条件，无法在同一列表中并排查看。

**方案**：把输入按英文逗号、中文逗号或空白切分，逐项去除可选 `#` 前缀、空项
和重复项；每项继续对全报告连续展示编号做模糊匹配，多个条件使用 OR 合并。

**验收**：`84,128`、`84， #128` 和空白分隔写法均同时返回对应问题；单编号、
模糊匹配、清空、严重度/类型/复核状态叠加过滤保持原行为；前端 build/lint、
真实记录页面冒烟和控制台检查通过。

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

**问题**：纯文本层无法发现固化在图片中的源语言文字。真实样例第 6 页
右下表格在源、目标渲染中像素完全一致，但 72 个中文字形对象均被 PDF
表示为图片，文本层只剩 IGBT、SiC 和数字，因此普通漏译检测没有语言
字符可读。其他视觉属性丢失、遮盖后果和非文本元素同样属于后续盲区。

**方案**：

1. **P1 图像指纹候选检测（已落地）**：Parser 对解码图片像素计算 SHA-256，
   只把摘要写入 Block metadata；ContentDetector 在页面主导脚本已变化时，
   聚合源目标指纹相同、位置和尺寸稳定的图片 Region。只有数量与覆盖面积
   同时达到 `RuleProfile` 阈值才生成 `UNTRANSLATED_RASTER`，单张照片、
   Logo 和零散装饰图不命中。该阶段零新增依赖、不开 OCR，也不保存图片正文。
2. **P2 候选区 OCR（已落地）**：除 P1 候选外，把位置尺寸稳定、面积足够且
   指纹已变化的大图片纳入候选，只渲染候选 BBox，不做整页 OCR。core 定义
   可注入、可关闭的 `OCRProvider`，server 提供本地 PaddleOCR 3.x 适配器；
   模型单实例复用并由 `DQA_OCR_ENABLED` 控制。源/目标候选区分别识别后比较
   主导脚本、字符数和置信度，确认图片标签部分漏译后复用
   `UNTRANSLATED_RASTER`，并把 OCR 框映射回 PDF 坐标。
3. **P2 证据与隐私**：Issue 仅保存候选 BBox、脚本占比、OCR 置信度和受限长度
   文本片段；不保存裁剪图片二进制，不把完整文档发送给远程 OCR。OCR 不可用、
   超时或低置信度时保留 P1 的确定性问题，不静默放过。
4. **P3 通用像素差分（待评估）**：复用 PyMuPDF Renderer，针对颜色变浅、
   水印和遮盖等问题评估 SSIM/形态学差分；保持独立开关，避免其噪声影响
   图像文字漏译规则和既有 Golden 基线。

**验收**：

- P1：第 6 页右下图像化表格聚合为一条可定位 Issue，单张照片/Logo 阴性；
- P1：图片摘要不包含二进制，阈值全部来自 `RuleProfile`；
- P2：OCR 可关闭、失败可降级、外部实现认证调用全部 Mock；
- P2：真实候选区能输出源/目标脚本占比与置信度，误报率经复核标注 < 20%；
- P3：人工构造改颜色/换图/加水印样例命中，默认关闭时 Golden 行为不变。

**落地记录（2026-08，P1/P2）**：

- `PyMuPDFParser` 新增解码图片像素摘要；`ContentDetector` 新增图像化文字
  未翻译聚类；`IssueType.UNTRANSLATED_RASTER` 与前端中文标签、说明同步。
- 汽车行业真实样例第 6 页右下区域识别为 72 个未变化图片 Region，目标 BBox
  约为 `x=508.5, y=265.0, width=399.8, height=221.5`。新质检记录
  `20260828-132503-019-1141`：7 页、176 个配对、20 个问题，最终分数
  91.00；该问题为第 19 条、高危，且只出现在第 6 页。
- `OCRProvider`、`RasterOCRDetector`、内存区域渲染与 server
  `PaddleOCRProvider` 已接入；PaddleOCR/PaddlePaddle 作为 server 可选依赖，
  模型缓存位于忽略版本控制的 `webapp-artifacts/ocr-cache`。OCR 关闭时默认
  CLI 基线仍为 20 个 Issue、91.00 分。
- OCR 开启的新记录 `20260828-140606-968-89dd`：处理 11/11 个候选，新增
  第 5 页两张图的中文图例和第 7 页右图中文标签共 3 条问题；第 7 页识别
  104 个残留中文字符，残留比例 33.1%、平均置信度 98.6%，超过 30 字符
  高危阈值后页面状态为 REVIEW。最终 23 个问题、87.86 分。误报率目标仍需
  积累人工复核样本后统计。

---

## T20 服务端持久化日志（按天轮转 + request_id 关联）

**问题**：服务端结构化 JSON 事件（observability.py）与 uvicorn 访问
日志仅输出到 stderr/stdout，进程一退出日志即丢失；事后排障（任务
失踪、启动崩溃、请求报障）没有持久证据可查。

**方案**（纯标准库，延续 observability 零依赖哲学）：

1. **落盘布局**：`webapp-artifacts/logs/` 下三个按天轮转文件——
   `server.jsonl`（JSON 事件，机器采集）、`access.log`（访问日志，
   人读）、`error.log`（应用异常与启动生命周期消息）。继承
   artifacts 目录的 gitignore；产物 GC 只扫 `pages/task-*`，不误删。
2. **轮转与保留**：`TimedRotatingFileHandler`（when=midnight）+
   `backupCount` 按天滚动、自动过期，磁盘占用有上界。多进程并发写
   不支持（当前单进程部署不受影响，文档如实标注）。
3. **接入时机**：`create_app` lifespan startup 调用
   `configure_file_logging`——晚于 uvicorn dictConfig，避免 handler
   被整体替换；幂等防 `--reload` 重复挂载。stderr/stdout 输出保持
   不变（12-Factor 约定，容器侧仍可走标准流采集）。
4. **请求关联**：新增纯 ASGI `RequestIdMiddleware`（api 层）——每
   请求生成 8 位 request_id 存 contextvar，`RequestContextFilter`
   自动注入 JSON 事件，并回写 `X-Request-ID` 响应头；后台任务继承
   提交请求的 request_id，访问日志与业务事件可互相印证。
5. **生命周期事件**：`server_started`（pid、日志路径、版本）/
   `server_stopped` 登记 KNOWN_EVENTS，作为排障时间线锚点。
6. **配置**：settings 新增 `log_file_enabled`（默认 True）、
   `log_dir`（默认 `artifacts_dir/logs`）、`log_retention_days`
   （默认 14），均可用 DQA_ 环境变量覆盖；关闭后退回纯标准流，
   历史行为零变化。

**验收**：

- 启动后三个日志文件生成，`server.jsonl` 首条为 `server_started`，
  access.log 记录到 HTTP 请求且与控制台访问行一致；
- JSON 事件携带 request_id 且与响应头 `X-Request-ID` 一致；
- `log_file_enabled=False` 时无文件产生，stderr 行为与历史一致；
- `python -m compileall -q server/src` 通过。

**落地记录（2026-08）**：

- `observability.py` 新增 `configure_file_logging`/`RequestContextFilter`
  与 request_id contextvar API；`api/middleware.py` 新增纯 ASGI
  `RequestIdMiddleware`；`api/app.py` 接入 lifespan 生命周期事件；
  `settings.py` 新增 `log_file_enabled/log_dir/log_retention_days`。
- 验证证据：真实样例 `POST /api/compare` 全链路——响应头
  `x-request-id: b426e0bc` 与 `task_submitted/running/done` 三条事件
  的 `request_id` 完全一致（后台任务经 contextvar 继承关联）；
  `server.jsonl` 记录到优雅停机的 `server_stopped`；access.log 与
  控制台访问行一致；`DQA_LOG_FILE_ENABLED=false` 时 logs 目录不
  创建且事件回退 stderr（`log_file: null`）；compileall 通过。
- 已知限制（已写入 docstring）：`TimedRotatingFileHandler` 不支持
  多进程并发写；当前单进程部署不受影响。

---

## T21 复核反馈自学习回路（误报归因 → 调优建议 → 定期闭环）

**问题**：复核闭环已持久化 `confirmed/false_positive/ignored` 判定，但
这些结论没有被回流用于检测调优——误报集中在哪些检测器、哪些场景，
只能靠人工翻报告，规则阈值校准（见 rule-calibration.md）缺乏持续
数据输入。

**方案（三阶段，人在环上，不做无人值守改阈值/黑盒 ML）**：

1. **P0 误报归因统计（已落地）**：`ReviewInsightService` 把
   `review_decisions` 关联到该文档对最新报告，按 Issue 类型聚合
   确认/误报/忽略分布与误报率；`GET /api/insights/review` 输出；
   规则管理页展示"误报归因统计"区块。无法归因的决策（重跑后
   Issue ID 变化）计入 unmatched 如实呈现。
2. **P1 调优建议生成**：从误报热区生成 RuleProfile 新版本草稿
   （DRAFT）——阈值微调建议（附 FP 的 metrics 分布证据）或
   `severity_overrides` 降级建议；生成后自动跑 Golden 回归，人工
   确认才升版本。需要 profile schema 扩展抑制规则（可选）。
3. **P2 定期闭环**：定时任务重放近期复核 → 生成候选 profile →
   Golden + 近期真实任务回归 → 全绿进待审批队列。

**明确不做**：无人值守直接修改生产阈值（违反契约 §12 可复核性）；
训练 ML 分类器过滤误报（FP 量级不够，违反"结构化证据"原则）。

**验收**：

- P0：`/api/insights/review` 返回与 `review_decisions` 一致的聚合
  （总决策数 = 确认 + 误报 + 忽略）；规则页可见误报热区排序；
- P1：建议产物是合法 RuleProfile 新版本，Golden 回归结果随建议
  一并呈现，未审批不生效；
- P2：闭环产物只进待审批队列，审计可查。

**落地记录（2026-08，P0）**：

- `server/.../services/review_insight_service.py`（聚合）+
  `api/routes_insights.py`（GET /api/insights/review）+
  `app.py` 装配；`frontend`：`api.ts` 类型与方法、`queryClient.ts`
  包装、`ProfileManager` 误报归因统计区块（按误报率排序，≥50% 红 /
  ≥25% 黄高亮）。
- 验证：真实库 17 条判定（1 确认 + 13 误报 + 3 忽略）→ 接口返回
  一致，12 条归因 + 5 条 unmatched；`number_mismatch` 3/3 误报率
  100% 排首位；frontend build/lint 通过。

**落地记录（2026-08，P1）**：

- core 新增 `document_qa/feedback.py`：`suggest_tuning` 纯函数——
  门控指标（契约 §6.4 metrics）分离窗口分析生成阈值建议 +
  严重度降级建议（fp_rate ≥70% 且判定 ≥3）；草案强制重过
  `RuleProfile` Schema 校验（含 severely_shifted_ratio 次序约束）。
- 防误导三闸门：误报 <2 条不建议；误报/确认指标窗口重叠不建议；
  指标超阈值 Schema 上限（数值杠杆失效）不建议。真实数据仅
  `number_mismatch`（3/3 误报、无数值杠杆）产出 severity 降级建议，
  region_shifted 因窗口重叠被正确拒判。
- server：`ReviewInsightService.tuning_advice`（基准取判定时引用的
  Profile 版本，缺失回退内置）+ `GET /api/insights/review/suggestions`；
  frontend：规则页"调优建议"区块 + "应用为 DRAFT 草案"（走既有
  profile 保存，只入库不生效）。
- 验证：构造样本 4 场景（正例窗口/重叠/超上限/单样本）全部符合
  预期；Golden 不变性——feedback 模块纯建议、不接入检测流水线，
  检测行为与 Golden 基线零变化；compileall + build + lint 通过。

**落地记录（2026-08，AI 修复报告）**：

- server 在既有只读归因链路上按 `issue_type + detector` 聚合误报，输出
  代表误报/确认对照、数值 metrics、疑似流水线阶段、代码检索起点、
  待验证问题与回归要求；根因统一标记为 `unverified`，不把代码提示
  包装成已确认结论。
- 新增 `GET /api/insights/review/repair-report` 结构化接口与 Markdown
  下载接口；证据文本明确标记为不可信内容并以 JSON 代码块承载，避免
  文档内容伪造报告指令。
- frontend 新增“AI 修复报告”摘要与按误报模式多选导出入口；原“调优
  建议”明确改名为“规则调优”，继续作为代码诊断后的可选分支。
- 验证：当前真实库生成 6 组误报诊断任务；接口、Markdown 下载、
  compileall、frontend build/lint 与 1280 px 桌面布局检查通过。

---

## T22 Python 工程治理与可复现构建

**问题**：双发行包缺少仓库级依赖解析和锁文件，README 的根目录安装与验证命令
已失效；Python 质量检查、类型边界、发行包构建和多版本兼容没有自动门禁。API
层仍直接导入部分 core 能力，SQLite 首版迁移使用 `executescript` 时可能在失败后
留下半成品 Schema，少量检测阈值也未进入 `RuleProfile`。

**方案**：建立 uv workspace 与统一 `uv.lock`，把 Ruff、mypy、coverage、build 和
HTTP 测试依赖放入开发依赖组；CI 覆盖 Python 3.11/3.12/3.14，并执行编译、静态
检查、边界类型检查、测试及双 wheel 构建。报告导出、解析异常和验证枚举收敛到
Service；SQLite 在不改写已发布迁移内容的前提下逐条执行脚本，并将单个迁移、
审计记录和 `user_version` 放入同一事务；剩余几何阈值进入 `RuleProfile`。
上述工程治理同时固化到 `docs/project-contract.md` §4.1、§9、§11、§12，作为后续
实现、评审和验收的强制基线。

**验收**：`uv lock --check` 通过；CI 三版本可从锁文件构建；API 源码不直接导入
`document_qa`；迁移注入失败后仅保留空的迁移审计表且可重新初始化；Ruff、渐进
mypy、`compileall` 和双发行包构建通过；检测默认值迁移前后真实样例各阶段摘要
及最终报告保持一致。

**当前证据（2026-08-28）**：锁文件、Ruff、mypy、compileall、11 项定向测试、
API 健康检查以及 core/server 的 sdist 和 wheel 构建已通过；真实样例 parse 阶段为
源文档 46 页/1360 Block、目标文档 46 页/15284 Block。完整测试当前 83 项中 4 项
失败（历史并发载荷兼容、数字展示值、Golden Sample 分数、文字图片重叠），后续
阶段和失败归因尚未完成，因此 T22 保持“实施中”。

---

## T23 比较任务子进程隔离（OCR 不再拖慢 API）

**问题**：开启 PaddleOCR（`DQA_OCR_ENABLED=true`）后，OCR 的 CPU 推理与 API 同
进程执行：单个比较任务期间 `/api/health` 等零逻辑接口延迟从毫秒级恶化到
1.3～13 s（系统负载 3.19），同文档对比较在任务重叠排队时由 84s 恶化到
126～149s，46 页文档比较耗时 36 分钟（任务 039e0739c5b7）。根因是进程内
CPU/GIL 饥饿，不是接口实现回归。

**方案**：比较任务改由 multiprocessing spawn 子进程执行（`services/
compare_worker.py`）。父进程（API）只经管道等待结果；单 worker 语义由原
`_run_lock` 保持（同一时刻最多一个子进程）；子进程 daemon 化，主进程退出
（含 --reload）即随之终止，中断任务由既有启动恢复逻辑标记 error。执行核心
抽取为模块级 `execute_compare`，同步路径（DQA_ASYNC_MODE=false / MCP）与
子进程共用，避免两套逻辑漂移。子进程按 `DQA_WORKER_THREADS`（默认 4，
0 不限制）写入 OMP/BLAS 线程上限，先于 numpy/paddle 导入生效；OCR Provider
在子进程内按 DQA_ 环境变量重建（其延迟初始化锁不可跨进程 pickle）。密码经
spawn 管道内存传递，不落盘。

**验收**：真实样例端到端——同文档对（IGBT 7 页，OCR 11 候选）隔离前后结论
一致（87.857 分 / review / OCR 11/11 / 历史入库且报告可回读）；隔离后比较
耗时 85.1s（隔离前 84s，无线程与进程开销回归）；比较运行期间 `/api/health`
与 `/api/samples` 延迟 1–9ms（隔离前实测 13000ms / 2500ms）。
`tests/test_compare_worker.py` 2 项通过；Ruff、compileall、mypy(settings)、
`uv lock --check` 通过。行为不变式：报告 Schema 与检测结论逐位一致；任务
生命周期（排队上限、终态 TTL、重启中断标记）不变；历史同事务持久化不变；
密码仅内存传递不变；core 零改动。

**证据（2026-08-28）**：任务 490598ab4cb5 子进程执行 85.1s 完成，历史记录
`20260828-160454-148-21dd`；比较期间 health 延迟采样 18 次全部 ≤9ms；对照
隔离前同文档对记录 `20260828-145855`（84s、87.857 分）与未隔离 46 页任务
039e0739c5b7（36 分钟、期间 health 13s）。

---

## T24 多机部署时的任务队列选型（Celery 评估，触发条件制）

**问题**：当前为单机单用户工作台，比较任务单 worker 串行；T23 子进程隔离已
解决 CPU 饥饿与接口拖慢问题。契约 §3.2 明确将任务队列排除在 MVP 范围外。
只有部署形态演进后，进程内任务注册表与单机互斥锁才会成为真实瓶颈。

**方案（触发条件制，不预先实施）**：以下任一条件成立时启动评估——
1) 出现多机部署或多 worker 横向扩展需求；2) 需要跨机器任务分发或定时批量
质检；3) 单机排队上限（当前 3）与单 worker 串行无法满足并发用户数。候选
方案 Celery（+ Redis/RabbitMQ Broker）；评估时必须按契约 §12 说明依赖体积、
许可证、安全与 Python 版本影响，先修订 §3.2 基线并获用户确认，同时设计
`async_tasks` 状态与 Broker 状态的兼容迁移。

**验收**：契约修订先行并留验收记录；选型对比（Celery / RQ / Dramatiq /
自研 worker 协议）附压测数据；任务状态机、失败重试、重启恢复与历史持久化
行为与单机版对齐。

---

## T25 评审修复第一批：越界容差 / 移页数字豁免 / 事务外哈希 / review_task_id 下发

**问题**：2026-08 全仓代码评审发现四处高优先级缺陷——
① `CONTENT_OUT_OF_PAGE` 零容差精确比较，字形上延、媒体框边缘的亚点级
溢出即判 Critical（按 §8 直接整篇 FAIL），且无容差参数、阈值未写入
metrics（违反 §6.4/§12）；
② 跨页对齐允许移页配对后，页眉/页脚中的页码、章节号随页码自然变化，
页面级数字守恒将其判为 missing+extra，每条 MEDIUM 起步，足以把正常
移页页面拖进 REVIEW；
③ 历史保存在 `BEGIN IMMEDIATE` 写事务内对源/目标文件流式计算
SHA-256（单文件上限 100 MiB），期间阻塞任务状态落库、复核保存等
全部并发写操作，超过 busy_timeout 即报 `database is locked`；
④ 复核任务 ID 由前端用 `source/target_document_id` 前 12 位自行拼接，
属未成契约的自造协议，前缀相同的文档对会串用同一份复核记录。

**方案**：

1. core：`DetectorThresholds` 新增 `out_of_page_tolerance_ratio`
   （默认 0.005，相对页宽/页高）；越界检测按轴计算溢出量，双轴均
   不超容差则不判，溢出量与容差写入 Issue metrics。
2. core：`DetectorThresholds` 新增
   `number_mismatch_margin_band_ratio`（默认 0.08，相对页高，0 禁用）；
   仅当源/目标页码不同（移页）时，完全位于上/下高度带内的区域不参与
   数字守恒；豁免比例与被豁免数字写入 metrics，非移页页行为不变。
3. server：`history_service._save` 把文件身份（SHA-256、size、
   availability）预计算移到事务外（`_file_identity`），事务内只做
   查询与插入；`sample_service` 的同类写法登记为后续项。
4. server：API 层在报告返回点（同步 compare、任务轮询、历史单条）
   注入 `review_task_id`，派生规则与既有复核记录完全一致
   （`source[:12]-target[:12]`，保证历史判定延续）；前端 ReportDetail
   优先使用服务端下发值，本地拼接仅作旧负载兜底。

**验收**：

- 新阈值全部定义在 `RuleProfile` 并写入 Issue metrics，检测器无新增
  裸阈值（§3/§6.4/§12）；
- 非移页真实样例检测行为不变式：parse/group/alignment/match 各阶段
  摘要与改造前一致；detect 阶段仅预期差异（越界/数字豁免）可见；
- ruff、渐进 mypy、compileall、双包构建、前端 build 通过；
- 分阶段真实样例验证（parse → report）逐阶段展示摘要并经用户确认。

**落地记录（2026-08）**：

- `uv lock --check`、Ruff、渐进 mypy（13 个边界文件）、compileall、
  core/server sdist+wheel 构建、frontend build 全部通过。
- 真实样例六阶段验证（un-china-2024 对）：parse 46 页 1360/15284
  Block、group 508/486 Region、alignment 46 对（0 缺失/0 新增）、
  match 459 对、detect 275 Issue、report fail/80.39；与改造前 HEAD
  基线 worktree 逐条比对，275 条 Issue 键集合与字段完全一致、分数
  逐位一致——该样例无移页、无边界越界，两处行为修复正确处于休眠，
  `margin_band_ratio=0.0` 已随 number_mismatch metrics 落盘。
- 构造用例正反验证：right/left 溢出 0.1/0.5pt 不再判 Critical（旧
  代码必报）、溢出恰等于容差（可精确表示的 3.0pt）被抑制（边界
  `<=`）、溢出 10pt 保留 Critical 且 metrics 带溢出量；移页 3→7 页脚
  页码差异豁免、正文数字/章节号差异照报（`margin_band_ratio=0.08`）、
  跨越带边界的区域不豁免、非移页页对页脚差异行为不变。
- 后续项：`sample_service` 同类事务内哈希待重构（低频路径，P2）。

---

## T26 评审修复第二批：检测可信度

**问题**：2026-08 全仓代码评审第二批发现——
① 代表样式取 Region 内**最大字号**块：源侧「20pt 标题 + 10pt 副题」合并
后代表为 20pt，目标侧换行/合并后与不同子块比较，既会假阳性触发
FONT_SHRINK HIGH，也会掩盖真实缩小（grouper/composer/matcher 三处联动）；
② 匈牙利分配对方阵强制全配：一侧 Region 因翻译合并消失时，后续 Region
整体顺延配对，产生一串 0.45～0.6 的伪匹配并连带成串 REGION_SHIFTED/
RESIZED 误报；
③ `RuleDetector`/`TextAlignmentDetector` 直接读全局 `detectors`，
`language_overrides` 对布局/字体/重叠/对齐检测不生效，与
`detector_settings_for` 的注释承诺矛盾；
④ `raster_ocr.py` 与 `content.py` 的脚本判定表不一致（kana 归属、阿语
数字区间），同一报告内 OCR 启用判断可能自相矛盾；
⑤ `pymupdf_parser` 背景提取 `except Exception: pass` 静默吞错（违反 §9），
且背景深色判定阈值（0.1/0.92/0.5）散落在解析器内未进 RuleProfile；
⑥ REGION_SHIFTED/FONT_SHRINK/REGION_RESIZED/碎片化/重叠等 Issue 的
metrics 缺少判定阈值（§6.4）。

**方案**：

1. core 新增 `style_stats.weighted_median_font_size`：grouper 与
   composer 的代表样式改用**字符数加权字号中位数**（样式身份与标题
   判定保持原逻辑），matcher 的 font_change 因此对比主体字号。
2. `MatchingSettings` 新增 `weak_match_score_floor`（0.6）与
   `weak_match_cost_penalty`（0.5）：得分低于可信线的代价项加罚，
   阻止强制分配用弱配对挤占强配对的目标列；`minimum_score` 过滤不变。
3. core 新增 `script_detection.py` 共享模块（判定表 + 主导脚本投票 +
   语言场景解析）：content/raster_ocr/RuleDetector/alignment 统一取
   `detector_settings_for(language)`，默认 overrides 为空故默认行为
   不变。
4. 解析器背景提取异常记入 page metadata（`background_parse_errors`），
   背景判定阈值收敛为 RuleProfile `BackgroundSettings`（默认值与原
   硬编码一致），pipeline 装配时传入。
5. 上述检测器 Issue metrics 补齐阈值字段。

**验收**：

- 默认行为差异仅限预期项：字号基线加权与匹配惩罚下限引起的
  FONT_SHRINK/REGION_SHIFTED/REGION_RESIZED 增减，逐条归因；
- language_overrides 生效路径有构造用例覆盖，默认 Profile 行为不变；
- ruff、渐进 mypy、compileall、双包构建通过；
- 分阶段真实样例验证 + HEAD 基线 worktree 逐条对照并归因。

**落地记录（2026-08）**：

- ①③④⑤⑥ 已落地：新增 `style_stats.weighted_median_font_size`
  （grouper/composer 代表样式保留最大字号块身份，字号改字符数加权
  中位数）；新增 `script_detection.py` 共享模块（脚本判定表 + 主导
  脚本投票 + `resolve_language`），content/raster_ocr/RuleDetector/
  TextAlignmentDetector 统一经 `detector_settings_for(language)` 取
  配置；解析器背景提取异常记入 page metadata
  `background_parse_errors`，背景判定阈值收敛为 RuleProfile
  `BackgroundSettings`（默认值与原硬编码一致，pipeline 装配传入）；
  182 条 Issue 的 metrics 补齐判定阈值字段。
- 构造用例：latin-cjk 覆盖关闭碎片化生效（0 条）且默认 Profile 同页
  照报（1 条）；同源 Block 混排 20pt/10pt 行的代表字号由 20.0 修正为
  10.0（加权中位数）。
- **② 低可信匹配惩罚下限：实现后经 Golden 否决并回退**。真实样例
  第 43 页存在 3 源 3 目标、其中一对无真实对应：无惩罚时匈牙利最优
  解让位置相似度 1.000/0.998 的真实配对保持不动、最差行承担剩余列
  （3 条可疑几何 Issue）；加入 0.6 悬崖惩罚后，求解器牺牲强配对
  （0.939→0.908、0.942→0.919）把弱配对抬过可信线，配对整体换位反
  而多产出 5 条伪几何 Issue（275→278，80.39→80.30）。惩罚悬崖制造
  了"跳崖激励"，与设计目标相反，已回退。候选替代方案（需另行评审）：
  a) 检测器侧可信门控——match.score 低于可信线的配对不产出
  REGION_SHIFTED/FONT_SHRINK/RESIZED（伪配对不再伪装成几何证据）；
  b) 平滑斜坡惩罚替代悬崖（Golden 显示该样例仍会换位，亦不推荐）；
  c) 维持现状（minimum_score=0.45 过滤已覆盖最差情形）。
- 验收：`uv lock --check`、Ruff、渐进 mypy、compileall、双包
  sdist+wheel 构建通过；真实样例六阶段——parse 46 页 1360/15284
  Block、group 508/486、alignment 46 对、match 459 对、detect 275
  Issue、report fail/80.39；与 HEAD 基线 worktree 逐条比对 275 条
  Issue 键集合、类型、严重度、描述与全部 font_size_change_ratio
  逐位一致（本轮改动在该样例正确休眠：单一样式 Region 的加权中位
  数等于原最大字号，language_overrides 未配置）。

---

## T27 M→1 合并区域 span 级字号对照

**问题**：真实记录 `20260831-055811-208-3c5e` 第 5 页，译文把两个图表
标题排进同一行（左标题保持 12pt、右标题压缩到 9pt，span 级证据确凿），
但系统零检出。归因：目标侧合并 Region `p5-r10` 与源左标题 `r7` 配对，
diff 已算出 font_change=-0.250（超 -0.20 阈值），却被
`_is_expected_translation_expansion`（译文变长且面积未缩 → 视为排版
适配）豁免；源右标题 `r7-c2` 未配对，MISSING 又被
`_is_covered_by_target_text`（交集比例 1.0 ≥ 0.40，多对一覆盖）豁免。
两条为正文误报设计的豁免联合吞掉了真实的标题字号缩小，且 -0.250
信号错位挂在未缩小的左标题配对上。

**方案**：只改 detect 阶段（`rules.py`），分组/匹配零改动。当匹配的
目标 Region 覆盖 ≥2 个文本源 Region（复用 `merged_text_coverage_ratio`
与 `intersection_ratio` 判定）时，区域级字号缩小判断不可信（合并代表
字号混入不同内容、豁免前提失效），改为把目标 Region 的文本 span 按
几何重叠最大者分配回各源 Region，按字符数加权中位数字号逐一对照：
`change < font_shrink_ratio` 即按 `font_shrink_bands` 出
FONT_SHRINK，BBox 锚定为该源 Region 对应 span 的并集，metrics 记录
span/source 字号与阈值。span 证据不可用（无带字号可见文本）时返回
None 回退既有区域级判断；font_grow 维持原逻辑。

**验收**：

- 构造用例：合并行字号一致不报（阴性）；单侧 span 缩小时报出且
  BBox/字号证据锚定正确（阳性）；
- IGBT 文档对端到端：`p5-r7-c2` 漏报转阳性，第 5 页其余 Issue 不变；
- Golden（un-china 对）六阶段 + HEAD 基线逐条对照，预期逐位一致
  （该路径仅在 M→1 合并时激活）；
- ruff、渐进 mypy、compileall、双包构建通过。

**落地记录（2026-08）**：

- `rules.py` 新增 `_detect_merged_font_shrink` 并接入 `_detect_geometry`：
  匹配目标 Region 覆盖 ≥2 个文本源 Region 时跳过区域级字号缩小判断，
  改为 span 分配后逐一对照（阈值复用 `merged_text_coverage_ratio` 与
  `font_shrink_ratio/bands`，无新增裸阈值）；span 证据不可用时返回
  None 回退既有逻辑；font_grow 维持原逻辑。
- 迭代一课：首版按"最大重叠面积"分配 span，Golden 第 24/25 页暴露
  误报——30pt 大标题 bbox 内一个 3×5pt 页码字符"1"被强行归属，
  产出 5pt vs 30pt 的 -83% 垃圾 HIGH。改为**双向实质覆盖门控**（复用
  `merged_text_coverage_ratio`）：span 大部分落在源 Region 内，且源
  Region bbox 被名下 span 实质覆盖，才允许对照。Golden 随即回到与
  基线逐位一致。
- 构造用例：合并行单侧 span 12→9pt 报 1 条 MEDIUM 并锚定缩小的源
  Region；字号一致 0 条；非 M→1 返回 None 回退；页码擦边形态 0 条。
- IGBT 文档对（记录 20260831-055811 的输入，OCR 关闭同条件）：
  HEAD 基线 20 条 / 91.00 分（与 T10 记录的 CLI 基线一致），新代码
  21 条 / 90.71 分——净差异恰好 +1：
  `p5-mfont-p5-r7-c2 font_shrink/medium`，源 `p5-r7-c2`（右图表标题）
  12pt → span 9pt（-25%），bbox=(584,228) 精确锚定右标题 span，
  metrics 含 `span_font_size/source_font_size/merged_region_compare`；
  其余 20 条逐条一致。
- Golden（un-china 对）六阶段：46 页 1360/15284 Block、508/486
  Region、46 对、459 匹配、**275 Issue / 80.3913 分与 HEAD 基线键
  集合、严重度、描述逐位一致**；`uv lock --check`、Ruff、渐进 mypy、
  compileall、双包 sdist+wheel 构建通过。
- 展示补充（2026-08，用户反馈"源图/译文图 #19 完全没对上"）：几何
  检测的 M→1 配对在 metrics 输出 `merged_source_count` 与
  `covered_source_bboxes`（新阈值 `merged_source_overlap_ratio=0.1`
  压境判定，收敛于 RuleProfile）；前端源图把合并块的其余源区域画为
  浅虚线框，详情明示"译文区域由 N 个源区域合并而来"；
  `number_mismatch`（页面级双锚点对比：缺失数字源区域 + 多出数字
  译文区域）增加"两个框各自锚定证据位置"的说明，消除"同内容两侧
  应重合"的误导。Golden 275 条逐位一致，22 条 M→1 配对获得证据
  标注，数量/分数/严重度零变化。
- 源图标注语义重构（2026-08，用户反馈原文侧标注仍会误导）：采用
  A+B 组合——A) 源图框改"参照语义"：蓝虚线（`PALETTE.info`）+
  蓝色角标变体（`IssueBadge tone="reference"`），与译文侧红色问题
  语义彻底分离，面板标注"蓝虚线框为所选问题的原文参照区域"；
  B) 源图标注默认隐藏，点击问题行后仅显示所选问题的参照框
  （M→1 合并块同时显示全部被覆盖源区域）。验证：默认无框、
  缺失类点击出蓝框、合并对出主框+覆盖框（浏览器实测），构建与
  lint 通过。

---

## T28 矢量图形元素对比（候选，范围缺口）

**问题**：排查记录 `20260831-094341-668-02b6`（#64 陪审证据）时确认：
源文档以矢量椭圆（4 段贝塞尔、浅蓝填充 `fs`）承载图表标签背景，译文
把整张图表重绘为位图（1437×511，英文标签烤进图片），椭圆随之丢失。
当前契约 §3.1 的解析范围是文本 Span、图片与基础样式——矢量绘图仅进
入解析器的背景色/深色块辅助信息（`background_color`/`dark_boxes`），
不作为可比较元素，因此"椭圆背景丢失"整体不可见。该页文本层破损
（残留中文碎片、CAGR 文本烤入图片）已被 28 条 Issue 充分捕获，但
"图形装饰丢失"这一交付风险属于检测盲区。

**方案（评估后细化）**：Parser 把含曲线/填充的矢量绘图对象（按
`get_drawings` 的 items/fill 归一化为"图形元素"：类型、BBox、填充色、
描边色）写入 Page 的独立只读集合；新增可开关的检测器，对源有目标无
（缺失）、或填充/描边色变更超阈值的图形元素出 Issue；阈值进
RuleProfile；评分走既有 `severity_overrides`/扣分上限。需评估图形
数量噪声（大文档绘图对象可达数千）与 LibreOffice 归一化的转换抖动。

**验收（初步）**：真实样例中椭圆缺失可检出并锚定；文本/图片既有
检测零回归（Golden 逐位一致）；可开关关闭时行为不变。

---

## T30 数量归一补全：英文缩写金额与裸英文月份

**问题**：AI 排查任务书（记录 `20260901-055449-715-519e`，#6 p1-numbers）：
Syneos 报告第 1 页报出 21 处数字差异（high）。逐项核对 PDF 原文后确认
译文数字完全正确，误报根因有二：(1) 图表分档 `$100M - $499M`、
`$1B - $4.99B` 等财务缩写金额不被 `_ENGLISH_SCALED` 识别（只认
thousand/million/billion 全词），降级为裸数字，而中文译文"1 亿 - 4.99
亿美元"被 `_CHINESE_SCALED` 正确换算，页面级守恒必然错位；(2) 侧栏
"in January at the 2025 Biotech Showcase"（裸英文月份，无相邻日期
数字）不被 `_ENGLISH_MONTH_DATE` 识别，中文"1月"却被识别，同一时间
状语两侧计数不对称（多余 1月）。

**方案**：`quantities.py` 新增 `_ENGLISH_ABBR_SCALED`（必须锚定货币
前缀 `US$/$/€/£/¥/USD/…`，单字母 k/m/b 后不得紧随字母或数字，排除
"Section 5B""100MB" 误判）与 `_ENGLISH_MONTH_BARE`（仅首字母大写的
月份名；may 作情态动词频率远高于月份语义，整体排除；只补位未被日期
相邻模式占用的跨度）。同时 `content.py` 的 number_mismatch metrics
新增 `comparison_scope: "page"`，澄清 source_text/target_text 是
独立选取的定位锚点而非互为译文的文本对。

**验收**：记录 `20260901-055449-715-519e` 第 1 页 21 处差异清零（复
跑流水线确认 p1-numbers 不再产生，文档分 51.71→53.14）；定向与新增
单元测试 26 条通过；examples 基线对 issue 数/分数/状态不变（竖排逐
字 span 页面 +1 月份 diff 的次生效应见 T31）。

---

## T31 竖排/逐字 span 文本的区域级可读性（候选，解析层局限）

**问题**：T30 验收时发现（examples 对 `un-china-2024`）：UN 类文档
译文页为竖排逐字 span（目标 15284 Block vs 源 1360），分组后区域文
本是字符乱流（如 `月␤…␤ 9 ␤`），"9月""12月17日"在单个区域内不连续，
`_CHINESE_MONTH` 等连续正则在该页区域级永远匹配不到。原始页面全文
层面数量两侧守恒，区域层面不可读——页面级数字守恒对这类页面系统性
偏向"源有目标无"。修复英文裸月份识别后，4 个此类页面各 +1 条月份
缺失 diff（页面上本已有其他数字 diff，issue 数/分数/状态不变）。

**方案（评估后细化）**：Parser 对竖排/旋转 span（`dir`/`line_mode`/
WMode）按列聚合或按视觉顺序重排后再拼接区域文本；或在分组层对逐字
span 做最小连贯性合并。需评估对既有分组/匹配/检测的波及面（该文档
对 237 条 Issue 的基线可能整体位移）。

**验收（初步）**：竖排页面的区域文本包含连续的"数字+月"片段；页面
级数字守恒在 raw 守恒的页面上不再产生新增月份缺失；Golden/既有检测
零回归或经 Golden 否决后再定。

---

## T32 碎片检测对混合脚本/拉丁完整短标签的保守误报

**问题**：T30 同族排查（记录 `20260901-063516-729-abe2`）中发现：CJK
纯中文两字词误报已由脚本豁免修复，但同一文档仍余 6 条 `text_fragmented`
渲染为完整横排标签："A轮/B轮/C轮"（拉丁+CJK 平票，`dominant_script`
返回 None）、"II期/I期"（拉丁主导）、"NDA"（纯拉丁完整缩写）。
用户复核确认："翻译过程中的缩写以及品牌名称"应予考虑——译文按惯例
原样保留这些 token，不是排版拆散。

**方案**：碎片检测引入**源页面级拉丁词形比对**——横向单行窄 Region
中的全部拉丁 token（casefold 归一）都能在源页面找到同一完整词时豁免
（"NDA"、"A轮"的 A、"II期"的 II）。取页面级而非配对区域级，因为图例
列的 M→1 配对可能错位（"A轮"配到"Seed"），词形证据仍应成立。被拆散
的片断（"SAE"→"SA"+"E"）在源页没有完整词形，仍按碎片报告；单字 CJK
窄 Region 与带换行竖排的既有判据不变。

**验收**：Syneos 对碎片 issue 6→0（A轮/B轮/C轮/NDA/II期/I期 全部消
除）；examples 对经影子基线（仅回退 T32）逐条对比，恰好移除 6 条
WHO/WFP/IOM/ILO/FAO/UNV 机构缩写误报、零新增（233→227，分数
81.70→81.91）；真实碎片（"P\nK"竖排、SAE 片断）单测保持报告。

---

## T33 横排单行长标题的 region_resized 宽度误报

**问题**：AI 排查任务书（记录 `20260901-065834-351-7098`）排查竖排
标签误报时发现的同族误报：横排**单行**标题/图题（如 p3
"Global IPOs and venture funding on the rebound"→"全球IPO和风险
融资回暖"、p6 "Figure 9. Relative demand…"→"图9.…"，共约 7 条）
宽度随译文字符密度自然缩短 -50%~-70%，被 region_resized 误报。
既有豁免 `_is_expected_text_width_change` 要求字数 ≤
`text_label_max_chars`（30），长标题超限后无法进入豁免；但单行
文本的宽度同样是墨迹长度（行宽由内容决定），与多行段落"列宽由
版式决定"有本质区别。同次排查已落地的竖排豁免
（`_is_expected_text_height_change`）按同一密度原理工作，横排
长标题是遗留对称缺口。

**方案**：将豁免的形态门控从"字数上限"扩展为"单行且宽度驱动"——
双方文本均无换行、宽度变化绝对值大于高度变化（墨迹轴判别）、字号
与高度稳定、宽度变化与全角/半角 advance 密度一致（复用
`text_advance_units` 与 `text_resize_length_tolerance_ratio`）。
多行图例类别丢失（如 4 行→1 行）因带换行被天然排除，不构成漏报。
需同步评估 30 字上限是否保留为双保险，并用 Golden Sample 回归
（§12：阈值语义变更需附 Golden 结果）。单行判别目前依赖文本换行
特征，已够用；若实施 T35 阶段二（方向元数据消费），墨迹轴判别可
同步升级为 dir 判别，两处共用聚合辅助函数。

**验收**：Syneos 对 p3/p5/p6/p7 的横排单行标题误报全部消除（约
7 条）；多行图例真实缺陷（4 行→1 行、2 行→1 行）保持报告；
examples 对与 Golden 回归零回归或漂移可解释。

---

## T34 数量归一补全二：英文基数词混排区间与中文纯乘数链单位声明

**问题**：AI 排查任务书（记录 `20260901-073417-801-1b76`，#1 p2-numbers）：
Syneos 报告第 2 页报出两个"多余数字"。逐项核对 PDF 原文后确认译文
数字完全正确，误报根因有二：(1) 源文 "may take **six to 12** months"
中的英文基数词 six 不被任何模式识别（`_NUMBER_PATTERN` 只认阿拉伯
数字），中文译文"6到12个月"的裸数字 6 被抽取，页面级守恒必然报
"多余 6"；(2) 译文图表 Y 轴竖排标题"交易总价值（**百万美元**）"
对应源文 "Total Value of Deals (USD $M)"——两侧都是单位声明而非
数量，英文侧 $M/in millions 因不含数字本来就不抽取，中文侧
`_CHINESE_SCALED` 却把"百"当计数数字、"万"当倍率换算出
quantity:1000000，单侧多余。用户追问"百万美元为何不在 #1 区域"：
`comparison_scope=page`，Issue bbox 只是含多余数字的目标区域锚点
（p2-r23 标题段），"百万美元"实际在 p2-r27（Y 轴标题），行为符合
metrics 注释约定，非定位缺陷。

**方案**：`quantities.py` 新增 `_ENGLISH_CARDINALS` 表与
`_ENGLISH_CARDINAL_RANGE` 混排区间模式：仅"一端阿拉伯数字、一端
基数词"的区间（six to 12）两侧换算为裸数字键——混写是明确的数值
信号，译文必然数字化；两端同类不处理（1.5 to 2 交由倍率区间模式
避免抢占 span、one to one → 一对一 识别反而制造缺失），区间后随
percent 时让位百分比模式保持 ratio 键。同时新增
`_PURE_MULTIPLIER_CHAIN`（`[十百千]+`）守卫：中文倍率表达数字部分
为纯乘数链（百万/千万/十万）即单位声明，不产生数量键；含计数数字
（三百万、十五亿）照常换算。阈值零新增，全部为抽取语义。

**验收与落地记录（2026-09）**：

- Syneos 对双跑对比：基线 166 条 / 63.14 分（与历史记录逐位一致）→
  修复后 165 条 / 63.71 分，唯一变化 p2-numbers 消失，零新增；
- examples 基线对（un-china）双跑逐条对比：227 条 / 81.91 分完全
  一致，零扰动；verify-stage 六阶段摘要：46 页 / 源 508 + 目标 486
  Region / 46 页对齐 / 459 配对 / 227 Issue / fail 81.91；
- 定向回归测试 `tests/test_quantities.py` 新增 12 例（混排区间 6 例
  含代词 one/百分比让位负例，纯乘数链 4 例含计数数字阳性对照），
  18 例全过。

---

## T35 文本方向元数据沉淀与消费（line dir/wmode 入 Block metadata）

**问题**：20260901 排查竖排标签误报（已落地
`_is_expected_text_height_change`）时发现：PyMuPDF `get_text("dict")`
的每个 line 自带精确书写方向（`dir` 单位向量，横排 `(1,0)`、竖排轴
标签 `(0,-1)`；`wmode` 区分旋转文本与真竖排 CJK），但
`pymupdf_parser._parse_text_block` 只读 span 字段，方向信息在解析层
即被丢弃。检测器只能用 BBox 窄高形启发式推断方向——对单行旋转标签
（业务文档旋转文本的绝对主流）已够用，理论边界为：单字符横排
Region（宽<高）误判竖排、非 90° 旋转、多行竖排。ROI 评估结论：
对当前已知误报清单直接清除量为零，单独实施不划算；但方向信号是
碎片检测宽度判据（`fragment_max_width`）、T31 竖排可读性、对齐
行向推断的共同升级路径，属基建型投入。

**方案**：分两阶段。
阶段一（零成本沉淀）：`_parse_text_block` 把 `line["dir"]`、
`line["wmode"]` 写入 Block.metadata——契约 §6.2 允许 metadata 保存
原始解析器信息，兼容变更、不动公开 Schema，让方向数据从落地日起
可持续沉淀，供未来任何回溯分析使用。
阶段二（消费端，按触发条件）：Region 级方向按子 Block 文本长度加权
多数票聚合（共享辅助函数），`_is_expected_text_height_change` 的
窄高形门控升级为 dir 判别并保留 metadata 缺失时的启发式回退（手工
构造 Region 的测试不携带 metadata）。触发条件任一满足即立项：
① 真实记录出现启发式方向误判的具体案例（升级 P2）；
② T31 或 T33 立项实施（搭车合并，边际成本近零）。

**验收**：阶段一——真实 PDF 解析后 metadata 含 `dir`/`wmode`（横排
`(1.0, 0.0)`、竖排轴标签 `(0.0, -1.0)`）；examples 分阶段验证零回归
（metadata 不参与任何既有判定，属纯增量字段）。阶段二——定向单测
覆盖加权多数票聚合与 metadata 缺失回退；Golden 回归零漂移或漂移
可解释。

---

## T36 匹配内容感知：数量签名否决 + 分配留空语义

**问题**：AI 排查任务书（记录 `20260901-093939-844-593f`，#13 p3-shift-p3-r13）：
源年份轴 `2011…2024*` 被配到目标轴标题合并行 `募资总额（百万美元）
$10,000$5,000…IPO单笔金额`，报出位置偏移。用户判断"不是同一处"成立。
根因链：① 翻译工具把源图表的竖排轴标题与部分刻度标签重排成横贯图表
的单行（渲染确认目标图表轴区确被破坏），分组器按同行墨迹忠实合并成
垃圾宽行；② 匹配器评分纯几何（位置中心距/尺寸/类型/顺序），无内容
项，中心距指标下"又宽又居中的垃圾行"比真正的年份行更接近源年份轴；
③ 匈牙利分配强制每个目标都配对（目标侧未匹配恒为空），垃圾行必然
抢走某个源的 partner，且被抢者的错配继续连锁（源脚注抢走目标年份行）。

**实验证据（2026-09 两组原型，均已回退）**：
- 裸数字集合否决（双方含数字且集合不相交→禁区代价 2.0）：修好第 3
  页但大面积破坏第 1 页——`$100M - $499M`↔`1亿‑4.99亿美元` 等数量级
  换算译文被误拆 8 对（分数 63.14→60.57）。结论：数字保值假设在中文
  数量词场景不成立。
- 数量签名否决（quantities 归一 key + 数量跨度外裸数字；$100M 与
  1亿美元同键）+ 未匹配哑行（代价=阈值成本）：净分 63.14→63.71，
  第 1 页 r24/r25 错配反被修复、第 3 页错配消除、第 2 页少 1 条数字
  误报；但第 4 页段落簇出现新连锁——r16 年份轴无正确对象，否决其垃
  圾配对后全局重优把 r37↔r5、r38↔r7 两对正确段落挤散（+3 条误报）。
  哑行对该簇无效：连锁配对均为 0.7+ 几何高分对，高于留空代价。
结论：逐格否决只能转移强制分配压力；内容盲评分无法区分"正确段落"
与"几何相似的错误段落"，需要方案级变更并经 Golden 校准。

**方案**：三层组合，一次性立项实施（匹配核心行为变更，按 §12 与
AGENTS 规则 2 需附 Golden 结果并经确认）：
① 匹配分数引入数量签名重合项（或作为硬否决），签名复用
`detectors/quantities.py` 的 `extract_quantity_mentions` 归一 key +
数量跨度外裸数字（全角归一保长度，span 对齐）；权重变化走
MatchingWeights 并以 Golden 重校准；
② 分配矩阵追加"未匹配哑行"（代价 = 1 − minimum_score），使低置信
配对在分配阶段即等价于留空——这是既有 minimum_score 过滤注释语义
（"低置信度不能伪装成有效匹配"）的全局一致化，让否决的压力有出口；
③ 排查 M↔N 逻辑分组为何未覆盖第 4 页的 1↔2 段落拆分
（r37→r5+r6、r38→r7+r8），必要时放宽 composer 的触发条件。
quantities 为在途模块，实施前需与其最终接口对齐；匹配器侧对
quantities 的导入须函数内延迟（避免 matching↔detectors 循环）。

**验收**：Syneos 对 p3 年份轴配对修正为 r19↔r14、脚注 r2↔r1，且第
1/4 页现有正确配对零破坏（逐对 diff 证明）；第 1 页 $100M↔1亿 等
数量级换算对全部保留；examples 对与 Golden 回归逐条对比，漂移可解
释并更新基线；新增单测覆盖：数量签名归一同键不相交否决、换算同键
不否决、哑行留空、1↔2 拆分（若 ③ 落地）。

---

## T37 任务动态可见化：记录页执行中任务 + 流水线阶段进度简报（已落地）

**问题**：20260901 用户提交 41 页 OCR 文档对（state-of-ai）后，质检
记录页完全不可见该任务：历史记录仅在任务完成时写入，而执行耗时约
20 分钟；前端轮询依赖工作台页内存状态，刷新即失明。后果有三：
① 用户误以为提交丢失（实际已在质检记录中排查确认任务在跑）；
② 诱导重复提交，而单 worker 串行会让排队越积越多；
③ 失败任务（如"报告持久化失败"）在任何列表中都不可见。
`async_tasks` 表本就随每次状态迁移落库，缺口只在 API 无列表端点、
前端不消费。

**方案**：两段式（同次落地）。
① 服务端 `GET /api/tasks`（limit 上限 100）：读 `async_tasks` 最近
任务，queued/running 附带进度简报；`GET /api/tasks/{id}` 同样附进度。
② core `DocumentQAPipeline.compare` 新增可选 `progress` 回调
（`ProgressListener`，阶段 parse/group/alignment/match/detect/ocr/
render/report + 页级 detail），回调异常静默吞掉不反噬主流程；
server 子进程经 `progress_path` 把事件追加写 JSONL（逐行刷盘，
`webapp-artifacts/tasks/<task_id>/progress.jsonl`），父进程轮询读
末行，无管道复杂度。前端记录页新增任务动态面板（5 秒轮询 +
1 秒耗时计时）：执行中/排队中始终展示（阶段步进器 + 一句话简报
+ 已耗时），失败任务展示近 24 小时窗口，done 不展示（直接进记录
表）；活跃任务清零时自动刷新记录列表。

**验收**（全部通过）：不变式——examples/un-china 对
progress=None 与带回调两次运行 `model_dump_json()` 逐位一致
（527,873 字节）；阶段摘要与既有基线吻合（46/46 页、508/486
区域、46 对、fail/81.91）；渲染分支事件（source/target 各 6 页）
与 JSONL 写入器临时目录用例通过。静态验收——`uv lock --check`、
ruff、渐进 mypy、compileall、双包 sdist/wheel 构建、前端
`bun run build` 全绿。端到端——API 重启后提交 IGBT 对：
`/api/tasks` 依次呈现 running + `ocr 第 3/7 页` 简报，浏览器记录
页面板实时显示阶段步进（解析✓→分组✓→对齐✓→匹配✓→逐页检测
高亮）与"已 1 分 3 秒"计时；完成后执行中行消失、新记录自动置顶
（35→36 条），验证用测试记录已删除还原。

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
