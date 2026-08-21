---
name: create-pure-component
description: Create or review presentational React components in the Structured Visual QA frontend. Use only when routing, data fetching, Query cache ownership, global business state, and page side effects stay outside the component; otherwise use create-react-feature.
---

# 创建纯展示组件

在 `frontend/` 内创建或修改纯展示组件，不借机迁移页面或改变业务流程。

## 上下文

除项目强制契约外，完整读取：

- `frontend/docs/design/frontend-architecture.md`；
- `frontend/docs/design/ui-guidelines.md`。

检查真实调用链、相邻组件、相关样式和现有共享实现。编辑前说明展示职责、纯组件
边界、放置位置和本次命中的 UI 契约。

## 组件边界

组件可以接收展示数据、回调、`className`、`children` 和标准 DOM 属性，但不得直接：

- 调用 `fetch`、Service、feature API 或 TanStack Query；
- 读取 Router、路由参数或 search params；
- 依赖全局业务状态、权限或跨页面副作用；
- 承担请求、轮询、缓存失效、持久化或业务编排。

允许保留不改变业务结果的局部交互状态。涉及页面路由、Query、API 或 feature 状态时，
由 `create-react-feature` 处理，展示数据和回调再通过 props 传入。

## 组件放置

| 场景 | 位置 |
| --- | --- |
| 应用壳层和全局布局 | `frontend/src/components/layouts/` |
| 无业务语义基础组件、Ant Design 轻封装 | `frontend/src/components/ui/` |
| 多个 feature 已稳定复用的展示组件 | `frontend/src/components/common/` |
| 单一 feature 的展示组件 | `frontend/src/features/<name>/components/` |

默认放在最近的 feature；“未来可能复用”不是提升理由。目标 feature 尚未迁移时允许在
当前调用方附近最小修改，不得仅为放置组件迁移整页。新目录按需创建，并优先复用
`components/ui` 的现有公开导出。

## 组件约定

- 使用 React 19、TypeScript 和现有 Ant Design 组件；
- 组件文件使用 PascalCase，目录使用小写或 kebab-case；
- Props 紧邻声明，只暴露展示所需数据和回调；
- 遵循相邻代码的导出方式，不使用 `React.FC`；
- 动态类名和外部 `className` 使用 `frontend/src/lib/cn.ts` 的 `cn()`；
- 公共组件和重要辅助函数使用简短中文 JSDoc；
- 禁止嵌套三元表达式；复杂分支使用具名变量、条件返回或小组件；
- 用户可见文案优先由 props 传入，不自行增加业务操作或说明。

视觉、表格、Tailwind、响应式、状态和可访问性完全遵循 UI 契约，不在本 Skill 重复定义。

## 验证

在 `frontend/` 运行 `bun run build` 和 `bun run lint`。有视觉变化时检查受影响页面、
控制台和 UI 契约要求的视口；有相关测试或重要展示分支时运行对应测试。
