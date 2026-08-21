import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router"
import { GlossaryPage } from "../../features/glossary/pages/glossary-page"
import { HistoryPage } from "../../features/history/pages/history-page"
import { RulesPage } from "../../features/rules/pages/rules-page"
import { SamplesPage } from "../../features/samples/pages/samples-page"
import { WorkbenchPage } from "../../features/workbench/pages/workbench-page"
import { validateWorkbenchSearch } from "../../features/workbench/model/workbench-search"
import { RootLayout } from "./root-layout"

const rootRoute = createRootRoute({ component: RootLayout })
const workbenchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: WorkbenchPage,
  validateSearch: validateWorkbenchSearch,
})
const historyRoute = createRoute({ getParentRoute: () => rootRoute, path: "history", component: HistoryPage })
const samplesRoute = createRoute({ getParentRoute: () => rootRoute, path: "samples", component: SamplesPage })
const rulesRoute = createRoute({ getParentRoute: () => rootRoute, path: "rules", component: RulesPage })
const glossaryRoute = createRoute({ getParentRoute: () => rootRoute, path: "glossary", component: GlossaryPage })

const routeTree = rootRoute.addChildren([
  workbenchRoute,
  historyRoute,
  samplesRoute,
  rulesRoute,
  glossaryRoute,
])

/** 一级页面真实路由：壳层保持挂载，每个 feature 直接绑定页面组件。 */
export const router = createRouter({ routeTree, defaultPreload: "intent" })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
