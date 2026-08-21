---
name: create-react-feature
description: Create, migrate, or review a Structured Visual QA frontend feature involving a route page, TanStack Router, TanStack Query, frontend API service, or page-owned business state. Use create-pure-component for presentation-only work and keep backend or core changes outside this skill.
---

# 创建 React Feature

在 `frontend/` 内按“统一壳层 + Feature-first”实现页面和业务能力，只修改目标 feature
与必要装配点。

## 上下文

除项目强制契约外，完整读取：

- `frontend/docs/design/frontend-architecture.md`；
- `frontend/docs/design/ui-guidelines.md`。

检查目标 URL、真实渲染链、API DTO、Query key、失效关系、公开入口和当前迁移状态。
编辑前说明状态所有权、数据流、装配点和保持不变的行为。

## 实施边界

- 页面、API、Query、模型、hook 和专用组件归 `features/<name>/`；按需创建目录；
- 一级页面归所属 feature，不建立全局 `pages/`；
- feature 外部只从 `index.ts` 导入，禁止跨 feature 深层引用；
- 跨 feature DTO 才进入 `contracts/`，其中不得放请求或业务逻辑；
- 纯展示单元同时遵循 `create-pure-component`；
- feature 未迁移时只移动完成当前需求所需的调用链，不顺手迁移其他页面。

## 页面与数据流

```text
Route Page
  → Query options
    → Feature API
      → services/httpClient.ts
```

- `AppShell` 只负责导航、布局状态和 `Outlet`，不得持有 feature 业务；
- 一级 URL 直接绑定 feature page，菜单状态来自 Router；
- 可分享筛选、分页和详情 ID 使用 typed search params；
- 服务端数据由 TanStack Query 持有，不长期复制到 `useState`；
- mutation 在所属 feature 内明确失效相关 key；
- route page 负责页面级 Query、错误/空状态和业务组件组合；
- `services/httpClient.ts` 是唯一 `fetch` 边界，不扩展集中式全局 `api` 门面。

跨 feature 协作按架构契约优先使用 URL、应用装配层或同一 Query 缓存，不用共享可变
单例，也不把业务状态提升到 `AppShell`。停止前端等待不等于取消服务端任务。

## 变更纪律

保持既有 URL、API DTO、状态语义和用户可见行为，除非用户明确要求改变。架构迁移
不得顺带重新设计页面，也不得修改 core、server Schema 或无关 feature。

## 验证

在 `frontend/` 运行 `bun run build` 和 `bun run lint`，并验证：

- 目标 URL 可直达、刷新和前进后退；
- Query 的加载、成功、空、错误和 mutation 失效；
- 有视觉变化时检查控制台和 UI 契约要求的视口；
- 有相关测试时运行对应测试；未配置测试时明确记录。
