import { createRootRouteWithContext, Outlet } from "@tanstack/react-router"
import type { QueryClient } from "@tanstack/react-query"

import type { CurrentUser } from "@/hooks/use-current-user"
import "@/styles/global.css"

/**
 * Root route. Carries the QueryClient via router context so loaders can call
 * `context.queryClient.ensureQueryData(...)` / `preload`. The document shell is
 * rendered here so login (outside the app shell) and the authenticated shell
 * both share the same <html>/<body>.
 *
 * `user` is filled in by the `__authenticated` route's `beforeLoad` guard and
 * made available to every authenticated child route via `context.user`.
 */
interface RouterContext {
  queryClient: QueryClient
  user?: CurrentUser
}

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        {children}
      </body>
    </html>
  )
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => (
    <RootDocument>
      <Outlet />
    </RootDocument>
  ),
  notFoundComponent: () => (
    <RootDocument>
      <div className="flex h-screen flex-col items-center justify-center gap-6 bg-ink-200 text-center">
        <div className="font-sans text-6xl font-bold leading-none text-ink-900">
          404
        </div>
        <p className="text-sm text-ink-700">未找到该页面</p>
        <a
          href="/"
          className="inline-flex h-9 items-center justify-center rounded-[var(--radius-DEFAULT)] bg-ink-900 px-4 text-sm font-medium text-ink-100 hover:bg-ink-800"
        >
          返回工作台
        </a>
      </div>
    </RootDocument>
  ),
})
