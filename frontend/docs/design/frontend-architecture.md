# Structured Visual QA 前端架构

状态：**核心路由迁移完成，API 与 views 收口中**

架构风格：**统一壳层（Unified App Shell）+ Feature-first**

适用范围：`frontend/`  
实现基线：2026-08-21

本文定义前端的目标结构和依赖边界。视觉规范见 [UI 契约](./ui-guidelines.md)，
产品与数据边界以 [`docs/project-contract.md`](../../../docs/project-contract.md) 为准。

## 1. 核心决策

1. 全站使用单一 `AppShell`，只承担导航、响应式布局和 Router `Outlet`。
2. 业务代码按 feature 组织，不建立独立的全局 `pages/` 层。
3. 页面、请求、Query、业务状态和专用组件归所属 feature。
4. Router 管理可分享页面状态，TanStack Query 管理服务端状态。
5. 跨 feature 调用经过公开入口；禁止引用其他 feature 的内部文件。
6. 保留 React、Ant Design、TanStack Router/Query 和 Tailwind CSS v4。
7. 采用渐进迁移，不改变现有 URL、后端 DTO 和质检行为。

## 2. 当前基线

当前代码已经完成统一壳层、五个一级真实路由、Workbench feature 状态与 URL
搜索参数接入；管理页仍通过 feature page 包装旧 `views/`，API 也尚未全部按 feature
拆分。当前剩余问题如下：

| 当前问题 | 目标 |
| --- | --- |
| `features/*/pages` 中部分页面只是旧 `views/` 的路由包装 | 把组件、请求和状态逐步迁入所属 feature |
| Router 仍深层导入 feature page | 各 feature 补公开入口后由装配层只引用公开 API |
| 部分页面仍以 `useEffect + useState` 保存服务端结果 | 使用声明式 Query，避免双状态 |
| `api.ts` 集中全部 DTO 和请求 | endpoint 按 feature 拆分，共享 DTO 进入 `contracts/` |
| `views/` 混合页面和内部展示组件 | 迁入所属 feature |
| `global.css` 混合全局和页面样式 | 全局样式与 feature 样式分离 |

## 3. 目标目录

只在职责实际迁移时创建目录，不预建空结构。

```text
frontend/src/
├── main.tsx
├── app/
│   ├── providers/
│   │   ├── AppProviders.tsx       # 全局 Provider 组合
│   │   └── queryClient.ts         # QueryClient 配置
│   ├── router/
│   │   └── router.tsx             # 路由树与 Router 实例
│   └── styles/
│       ├── global.css             # 全局元素与 Token
│       └── theme.ts               # Ant Design 主题映射
├── components/
│   ├── layouts/
│   │   └── AppShell.tsx           # 唯一应用壳层
│   ├── ui/                         # 无业务语义基础组件
│   └── common/                     # 多 feature 稳定复用组件
├── features/
│   ├── workbench/
│   ├── history/
│   ├── samples/
│   ├── rules/
│   └── glossary/
├── contracts/                     # 被多个 feature 使用的 API DTO
├── services/
│   └── httpClient.ts              # 唯一 fetch 边界
└── lib/
    └── cn.ts                      # Tailwind 类名合并
```

单个 feature 按需采用以下结构：

```text
features/history/
├── api/
│   ├── historyApi.ts              # endpoint 与本 feature DTO
│   └── historyQueries.ts          # query keys、options、失效策略
├── components/                    # feature 专用展示组件
├── pages/
│   └── HistoryPage.tsx            # 路由级页面
├── model/                          # 内部类型与数据转换
├── hooks/                          # 可复用的 feature hook
└── index.ts                       # 唯一公开入口
```

`api/`、`components/`、`model/` 和 `hooks/` 均为可选目录。单次使用的逻辑留在调用处。

## 4. 模块职责

| 模块 | 负责 | 不负责 |
| --- | --- | --- |
| `main.tsx` | 挂载 React 根节点 | 路由判断、请求、业务状态 |
| `app/` | Provider、Router、全局主题装配 | feature 业务实现 |
| `AppShell` | Logo、一级导航、响应式布局、`Outlet` | 数据请求、任务轮询、页面分发 |
| `features/<name>` | 页面、请求、Query、状态、模型和专用组件 | 修改其他 feature 内部状态 |
| `contracts/` | 两个及以上 feature 共用的后端传输类型 | 页面模型、请求方法、业务逻辑 |
| `components/ui` | 无业务语义原语和 AntD 轻封装 | feature 状态和请求 |
| `components/common` | 已确认跨 feature 复用的展示组件 | 预期复用但尚未发生的组件 |
| `services/httpClient.ts` | JSON、FormData、Blob 和统一错误处理 | history、rules 等业务概念 |
| `lib/` | 无业务语义、无副作用工具 | feature 用例编排 |

### 4.1 Feature 归属

| Feature | 职责 | 路由 |
| --- | --- | --- |
| `workbench` | 文档选择、发起质检、任务轮询、报告展示 | `/` |
| `history` | 质检记录查询、筛选、详情、重开报告 | `/history` |
| `samples` | 样本及语言对维护 | `/samples` |
| `rules` | 规则配置与启停 | `/rules` |
| `glossary` | 术语库与术语条目维护 | `/glossary` |

`QAReport` 等被工作台和质检记录共同使用的传输类型放在 `contracts/`；只属于单个
endpoint 的请求或响应类型留在对应 feature 的 `api/`。

### 4.2 组件放置

| 场景 | 位置 |
| --- | --- |
| 应用壳层和全局布局 | `components/layouts/` |
| 无业务语义基础组件 | `components/ui/` |
| 多个 feature 已稳定复用的展示组件 | `components/common/` |
| 单一 feature 的展示组件 | `features/<name>/components/` |

默认放在最近的 feature。“未来可能复用”不是提升到共享层的理由。

## 5. 依赖规则

```text
main → app
app → layouts / shared components / feature public APIs
feature → contracts / shared components / services / lib
shared components → lib
services → lib
```

强制规则：

- feature 外部只能从 `features/<name>/index.ts` 导入；
- 禁止 `feature → app`、`shared component → feature`；
- 禁止跨 feature 深层导入；
- 展示组件不得直接使用 Query、Router、全局业务状态或 `fetch`；
- `fetch` 只能存在于 `services/httpClient.ts`；
- `contracts/` 只保存传输类型，不得成为新的公共杂物目录。

跨 feature 协作优先使用 URL、应用装配层或 Query 缓存。只有无明确 feature 归属且
已有稳定复用的能力，才允许进入共享层。

## 6. 路由与状态

```text
AppShell
├── /          → WorkbenchPage
├── /history   → HistoryPage
├── /samples   → SamplesPage
├── /rules     → RulesPage
└── /glossary  → GlossaryPage
```

- `AppShell` 使用 `Outlet`，不得根据 pathname 手工选择页面；
- 菜单激活态来自 Router；分页、筛选、详情 ID 等可分享状态使用 typed search params；
- 服务端数据由 TanStack Query 持有，不长期复制到 `useState`；
- 编辑草稿、Drawer、Modal 等局部状态归最近的 feature 组件；
- 侧栏折叠、移动导航开关等纯布局状态归 `AppShell`；
- 工作台提交、轮询、停止等待和报告状态已经迁入 `features/workbench`；后续继续把
  其集中式 API 调用与旧 `views/` 展示组件收口到 feature。

## 7. Query 与 API

```text
Feature Page
  → feature query options
    → feature API
      → httpClient
        → /api
```

- 页面或 feature 容器使用 `useQuery`、`useMutation`；
- query key 必须包含影响结果的参数；
- mutation 成功后由所属 feature 明确失效相关 key；
- feature API 声明 endpoint 和单 feature DTO；
- 展示模型转换放在 feature `model/`；
- 不再扩展当前集中式 `api.ts` 和命令式全局 `api` 门面。

停止前端轮询不等于取消服务端任务。后端没有取消协议时，UI 只能表达“停止等待”。

## 8. UI 与样式

- Ant Design 负责 Table、Form、Modal、Drawer、Select 等复杂交互；
- Tailwind CSS v4 使用 `tw:` 前缀，只负责布局、响应式和组合样式；
- 动态类名统一使用 `cn()`；
- Token、AntD Theme 和全局样式归 `app/styles`；
- feature 样式与 feature 相邻，不进入全局 CSS；
- 具体视觉实现遵循 [UI 契约](./ui-guidelines.md)。

## 9. 迁移顺序

1. **壳层与路由（已完成）**：Provider、Router、`AppShell` 和五个 URL 已直接绑定
   feature page。
2. **工作台状态（已完成）**：提交、轮询、停止等待、历史恢复和报告 URL 状态已迁入
   `features/workbench`。
3. **管理页面（进行中）**：按 `history → samples → rules → glossary` 迁移 Query、
   API、页面组件和样式；当前仍有旧 `views/` 包装。
4. **收口（待完成）**：删除无调用者的 `views`、集中 `api.ts` 门面和页面级全局
   样式，补充 feature 公共入口与关键测试。

每个阶段保持 URL、API DTO 和用户可见业务行为不变，并独立完成构建与页面回归。

## 10. 验收标准

- `AppShell` 只负责导航、布局和 `Outlet`；
- 五个一级 URL 均绑定所属 feature page，支持直达、刷新和前进后退；
- `App.tsx` 不再承担页面分发和工作台业务；
- 请求、Query 和业务状态归所属 feature，共享 DTO 归 `contracts/`；
- 不存在跨 feature 深层导入或展示组件直接请求数据；
- `fetch` 仍只存在于 `services/httpClient.ts`；
- `/api` DTO、质检状态语义和报告结构保持不变；
- `bun run build`、`bun run lint`、`git diff --check` 通过；
- 375、768、1024、1280、1440 px 不出现页面级横向溢出。

认证权限、国际化、生产部署基路径、浏览器支持矩阵和性能预算当前证据不足，
不作为本次目录迁移的前置设计。
