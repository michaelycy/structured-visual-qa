# 需求待办：技术采纳方案（T1–T19）

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
| T13 | 前端 UI 契约与页面组件基线 | 🟡 实施中（质检记录契约化完成） | P1 | 2–3 天 |
| T14 | 前端路由与服务端状态统一 | ✅ 已落地 | P1 | 1–2 天 |
| T15 | Tailwind CSS v4 受约束接入 | ✅ 已落地（未批量迁移页面） | P2 | 0.5 天 |
| T16 | M↔N 逻辑文本分组匹配 | ✅ 已落地 | P1 | 1 天 |
| T17 | 跨行样式与条目边界安全分组 | ✅ 已落地 | P1 | 0.5 天 |
| T18 | 文本重叠双轴判定与双语证据 | ✅ 已落地 | P1 | 0.5 天 |
| T19 | 问题编号多条件过滤 | ✅ 已落地 | P2 | 0.25 天 |

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
- **T13 第一阶段（2026-08）**：新增 `docs/ui-guidelines.md` 与六个页面基础组件，
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

1. 新增 `docs/ui-guidelines.md` 作为可验收 UI 契约，量化色彩、字体、间距、
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
