import { AppShell } from "../../components/layouts/app-shell"
import { WorkbenchProvider } from "../../features/workbench"

/** 路由根布局：组合应用壳层与跨页面的工作台 feature 状态。 */
export const RootLayout = () => (
  <WorkbenchProvider>
    <AppShell />
  </WorkbenchProvider>
)
