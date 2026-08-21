# Structured Visual QA Frontend

React 19 + Vite + Ant Design + TanStack Router/Query 前端。

## 开发

```bash
bun install
bun run dev
bun run build
bun run lint
```

开发服务默认监听 `127.0.0.1:5180`，`/api` 代理到 `127.0.0.1:8765`。

## 样式职责

- Ant Design：Table、Form、Drawer、Modal 等复杂交互组件。
- Tailwind CSS v4：布局、Flex/Grid、响应式和组合样式。
- `global.css` / `uiTokens.ts`：全局设计 Token 和 Ant Design 主题来源。
- `components/ui/`：项目级基础组件。

Tailwind 使用 `tw:` 前缀并关闭 Preflight。只允许使用映射到 UI 契约的 `qa`
视觉 Token，例如：

```tsx
<section className="tw:flex tw:gap-qa-4 tw:rounded-qa-md tw:bg-qa-surface tw:p-qa-6">
  <h2 className="tw:text-qa-title tw:text-qa-text">标题</h2>
</section>
```

动态类名和外部传入的 `className` 统一通过 `src/lib/cn.ts` 合并：

```tsx
import { cn } from "./lib/cn"

<section className={cn("tw:p-qa-4", expanded && "tw:p-qa-6")} />
```

`cn()` 已配置识别 `tw:` 前缀，上例最终只保留 `tw:p-qa-6`。
禁止在组件中重复使用数组 `join` 或字符串拼接实现相同能力。

禁止使用 Tailwind 默认色板、任意值绕过契约，或用工具类重写 Ant Design 内部结构。
完整规则见 `docs/ui-guidelines.md` §15.1。
