import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router"
import { App } from "./App"

const rootRoute = createRootRoute({ component: App })

const workbenchRoute = createRoute({ getParentRoute: () => rootRoute, path: "/" })
const historyRoute = createRoute({ getParentRoute: () => rootRoute, path: "history" })
const samplesRoute = createRoute({ getParentRoute: () => rootRoute, path: "samples" })
const rulesRoute = createRoute({ getParentRoute: () => rootRoute, path: "rules" })
const glossaryRoute = createRoute({ getParentRoute: () => rootRoute, path: "glossary" })

const routeTree = rootRoute.addChildren([
  workbenchRoute,
  historyRoute,
  samplesRoute,
  rulesRoute,
  glossaryRoute,
])

/** 一级页面路由：应用外壳保持挂载，业务页由 URL 决定。 */
export const router = createRouter({ routeTree, defaultPreload: "intent" })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
