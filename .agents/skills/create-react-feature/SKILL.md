---
name: create-react-feature
description: Create, modify, migrate, refactor, or review a feature, route page, TanStack Router route, TanStack Query workflow, frontend API service, or page-owned business state in the Structured Visual QA frontend. Use when work goes beyond a pure presentational component; keep backend and core changes outside this skill.
---

# 创建 React Feature

在 `frontend/` 中按“统一壳层 + Feature-first”架构实现页面和业务能力。只修改用户要求的
feature 与必要装配点，不借机迁移其他页面、改变 API DTO 或重构后端。

## 必读上下文

开始前完整读取：

1. `AGENTS.md`；
2. `docs/project-contract.md`；
3. `frontend/docs/design/frontend-architecture.md`；
4. `frontend/docs/design/ui-guidelines.md`。

随后检查：

- 目标 URL、当前 route 和真实渲染链；
- feature 的调用方、API endpoint、DTO、Query key 与失效关系；
- 相邻 feature 的公开入口和已有共享组件；
- 当前代码处于迁移前结构还是目标结构。

第一次编辑前说明目标 feature、状态所有权、数据流、装配点和保持不变的行为。

## Feature 边界

业务能力默认放在 `frontend/src/features/<name>/`，按需使用：

```text
features/<name>/
├── api/                 # endpoint、本 feature DTO、query options
├── components/          # feature 专用展示组件
├── pages/               # 路由级页面
├── model/               # 内部模型与纯转换
├── hooks/               # 可复用的 feature hook
└── index.ts             # 唯一公开入口
```

- 不为结构完整预建空目录；
- 一级页面归所属 feature，不创建全局 `pages/`；
- feature 外部只从其 `index.ts` 导入；
- 禁止访问其他 feature 的内部文件；
- 两个及以上 feature 共用的后端传输类型放入 `frontend/src/contracts/`；
- `contracts/` 只保存 DTO，不放请求方法、展示模型或业务逻辑；
- 纯展示单元同时遵循 `create-pure-component`。

目标 feature 尚未迁移时采用最小迁移：只移动完成当前需求所必需的调用链，并保持旧
入口可工作或同步更新其唯一调用方。不得顺手迁移无关 feature。

## 统一壳层与路由

`AppShell` 只负责 Logo、一级导航、响应式布局、布局状态和 Router `Outlet`。
不得把 feature 请求、任务轮询、筛选、表单或报告状态提升到壳层。

- 每个一级 URL 直接绑定所属 feature page；
- 菜单激活态来自 Router，不复制 pathname 为菜单 state；
- 分页、筛选、详情 ID 等可分享状态使用 typed search params；
- route tree 在 `frontend/src/app/router/` 装配；
- feature 不得反向依赖 `app/`；
- 不为没有真实性能证据的页面预先增加懒加载或 route prefetch。

## 状态所有权

| 状态 | 所有者 |
| --- | --- |
| URL、分页、可分享筛选、详情 ID | TanStack Router |
| 服务端数据、请求状态、缓存 | TanStack Query |
| feature 流程和轮询控制 | feature page、容器或 hook |
| 编辑草稿、Drawer、Modal、当前行 | 最近的 feature 组件 |
| 侧栏折叠、移动导航开关 | `AppShell` |

服务端查询结果不得长期复制到 `useState`。只有编辑草稿或明确的时间点快照可以创建
有生命周期的本地副本。

## Query 与 API

数据流保持：

```text
Feature Page
  → feature query options
    → feature API
      → services/httpClient.ts
        → /api
```

- 页面或 feature 容器使用 `useQuery`、`useMutation`；
- query key 包含所有影响结果的参数；
- mutation 在所属 feature 中明确失效相关 key；
- endpoint 和单 feature DTO 放在 feature `api/`；
- 跨 feature DTO 放在 `contracts/`；
- API DTO 到展示模型的转换放在 feature `model/`；
- `services/httpClient.ts` 是唯一直接调用 `fetch` 的文件，且不得理解业务概念；
- 不扩展集中式 `api.ts` 或命令式全局 `api` 门面。

异步质检任务归 `workbench`。停止前端等待不等于取消服务端任务；后端没有取消协议时，
不得在 UI 或状态中伪装为已取消。

## 页面与组件组合

- route page 负责页面级 Query、错误/空状态和业务组件组合；
- 业务 hook 只在同一 feature 内复用，不作为跨 feature 通道；
- 展示组件只接收数据和回调，不直接读取 Router 或 Query；
- 组件按真实复用范围放入 `features/<name>/components`、`components/common`、
  `components/ui` 或 `components/layouts`；
- 优先复用现有基础组件和 Ant Design，不复制公共 CSS；
- 页面视觉必须遵循 UI 契约，不因架构迁移重新设计页面。

## 跨 Feature 协作

按以下顺序选择：

1. URL 或 typed search params；
2. `app/router` 等应用装配层组合公开入口；
3. TanStack Query 缓存中的同一服务端资源；
4. 已有稳定复用后提炼共享 DTO、组件或无业务工具。

不要用跨 feature 深层 import、共享可变单例或把业务状态提升到 `AppShell` 规避边界。

## 变更纪律

- 保持现有 URL、API DTO、状态文案和用户可见业务行为，除非用户明确要求改变；
- 不修改 core 检测逻辑、阈值、评分或 server Schema；
- 不运行全局格式化；
- 不一次性搬迁全部 `views/`、`api.ts` 或全局样式；
- 删除旧文件前确认无调用者，并检查用户未提交改动；
- 新依赖、认证、CORS 或环境配置变更必须单独说明影响。

## 验证

按改动范围完成最小充分验证：

1. 在 `frontend/` 运行 `bun run build` 和 `bun run lint`；
2. 运行 `git diff --check` 并检查只包含目标 feature 与必要装配点；
3. 验证受影响 URL 的直达、刷新、前进和后退；
4. 验证 Query 的加载、成功、空、错误和 mutation 失效行为；
5. 有视觉变化时检查控制台以及 375、768、1024、1280、1440 px；
6. 有相关测试时运行对应测试；未配置测试时明确记录，不以构建代替行为验证；
7. 纯前端 feature 改动不运行 PDF `--verify-stage`，除非触及 core 或用户明确要求。
