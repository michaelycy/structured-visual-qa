---
name: create-pure-component
description: Create, modify, refactor, or review pure presentational React components in the Structured Visual QA frontend. Use for components without routing, data fetching, Query cache ownership, global business state, or page-owned side effects; use create-react-feature when those concerns are required.
---

# 创建纯展示组件

为 `frontend/` 创建边界清晰、符合 UI 契约的 React 纯展示组件。保持改动局部，
不得借组件任务迁移页面、改变业务流程或扩展功能。

## 必读上下文

开始前完整读取：

1. `AGENTS.md`；
2. `docs/project-contract.md`；
3. `frontend/docs/design/frontend-architecture.md`；
4. `frontend/docs/design/ui-guidelines.md`。

随后检查目标组件的真实调用链、相邻组件、相关样式和已有共享实现。第一次编辑前说明：

- 组件的展示职责；
- 为什么属于纯组件；
- 按真实复用范围确定的放置位置；
- 本次实际命中的 UI 契约。

## 纯组件边界

组件可以接收展示数据、回调、`className`、`children` 和适用的标准 DOM 属性。
组件不得直接：

- 调用 `fetch`、`services/`、feature API 或 TanStack Query；
- 读取 Router、路由参数或 search params；
- 依赖全局业务状态、页面权限或跨页面副作用；
- 承担请求、轮询、缓存失效、持久化或业务流程编排。

业务逻辑由 feature page、容器或 hook 完成，再通过 props 传入。允许保留不改变业务
结果的局部交互状态，例如展开、聚焦或纯视觉开合。

需求一旦涉及页面路由、Query、API 或 feature 状态，使用 `create-react-feature` 处理
这些职责；本 Skill 只负责其中可独立拆出的展示单元。

## 组件放置

| 场景 | 位置 |
| --- | --- |
| 应用壳层和全局布局 | `frontend/src/components/layouts/` |
| 无业务语义基础组件、Ant Design 轻封装 | `frontend/src/components/ui/` |
| 多个 feature 已稳定复用的展示组件 | `frontend/src/components/common/` |
| 单一 feature 的展示组件 | `frontend/src/features/<name>/components/` |

默认放在最近的 feature。只有多个独立 feature 已存在稳定复用，才提升到 `common/`；
只有无业务语义的原语才进入 `ui/`。“未来可能复用”不是提升理由。

- 目标 feature 尚未迁移时，允许在当前调用方附近做最小修改，不得仅为放置组件而迁移整页；
- 新目录只在本次确有文件时创建；
- `components/ui/` 的公共导出遵循现有 `index.ts`；
- 优先复用 `PageHeader`、`PageSection`、`DataTable`、`StatusTag`、`EmptyState` 和 `FormDrawer`。

## 组件约定

- 使用 React 19、TypeScript 和现有 Ant Design 组件；
- 组件文件沿用项目 PascalCase，例如 `DocumentSummary.tsx`；目录使用小写或 kebab-case；
- Props 紧邻组件声明，只暴露展示所需数据和回调；
- 遵循目标目录现有导出风格，不使用 `React.FC`；
- 动态类名和外部 `className` 必须使用 `frontend/src/lib/cn.ts` 的 `cn()`；
- 需要 ref 时使用 React 19 当前类型，不新增 `MutableRefObject`；
- 公共组件和重要辅助函数使用简短中文 JSDoc；
- 禁止嵌套三元表达式；复杂分支使用具名变量、条件返回或小组件；
- 用户可见文案优先由 props 传入；必须内置时沿用系统现有中文术语；
- 不自行增加 Alert、确认流程、Tooltip 文案或业务操作。

## 视觉实现

- Ant Design 负责 Table、Form、Drawer、Modal、Select 等复杂交互；
- Tailwind CSS v4 只负责布局、响应式和组合样式，必须使用 `tw:` 前缀；
- 仅消费现有 `qa-*` Token，禁止默认色板、任意值、裸颜色和页面自造断点；
- 不启用 Preflight，不用工具类覆盖 Ant Design 内部结构；
- 优先使用扁平分区、间距和边框，不自动增加 Card、阴影、渐变或装饰动效；
- 表格内容使用 `DataTable`，不得覆盖 Ant Design 默认表头或固定表头、单元格高度；
- 时间列保持单行，通过合理列宽容纳，不缩小正文。

## 可访问性与状态

- 使用语义化元素和 Ant Design 可访问控件，不使用可点击 `div`；
- 图标按钮必须有 `aria-label` 和 Tooltip；
- 状态必须包含文字，不能只依赖颜色；
- 保留键盘焦点和阅读顺序，图片提供准确 `alt`；
- 动效支持 `prefers-reduced-motion`；
- 加载、空和错误展示优先复用现有基础组件，重试请求仍由调用方执行。

## 验证

按风险执行最小充分验证，不运行全局格式化：

1. 在 `frontend/` 运行 `bun run build` 和 `bun run lint`；
2. 运行 `git diff --check` 并检查目标文件差异；
3. 有相关测试或新增重要展示分支时运行对应测试，不机械新增快照；
4. 有视觉变化时检查受影响页面和控制台；响应式组件检查 375、768、1024、1280、1440 px；
5. 纯展示改动不运行 PDF `--verify-stage`，除非同时触及 core 或用户明确要求。
