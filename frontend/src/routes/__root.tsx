import { createRootRouteWithContext, Link, Outlet } from "@tanstack/react-router"
import type { QueryClient } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
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
 *
 * Monochrome error pages (docs §D3): 404 notFoundComponent + 500
 * errorComponent both render large bold status codes in black/white — no red
 * panic color (单色原则).
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

/** Monochrome error shell: large bold status code + explanation + actions.
 *  Shared by 404 + 500 — black/white only, no red. */
function ErrorShell({ code, explanation }: { code: string; explanation: string }) {
  return (
    <RootDocument>
      <div className="flex h-screen flex-col items-center justify-center gap-6 bg-ink-200 px-6 text-center">
        <div className="font-sans text-7xl font-bold leading-none text-ink-900">
          {code}
        </div>
        <p className="max-w-md text-sm text-ink-700">{explanation}</p>
        <div className="flex items-center gap-3">
          <Button onClick={() => window.history.back()} variant="secondary">
            返回上一页
          </Button>
          <Link to="/">
            <Button>返回工作台</Button>
          </Link>
        </div>
      </div>
    </RootDocument>
  )
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => (
    <RootDocument>
      <Outlet />
    </RootDocument>
  ),
  notFoundComponent: () => (
    <ErrorShell
      code="404"
      explanation="未找到该页面。它可能已被移动、归档，或您没有访问权限。"
    />
  ),
  errorComponent: ({ error }) => {
    // Log to console for dev triage; the user only sees the monochrome 500 page.
    // eslint-disable-next-line no-console
    console.error("Route error:", error)
    return (
      <ErrorShell
        code="500"
        explanation="页面加载出错，请稍后重试。如问题持续，请联系管理员。"
      />
    )
  },
})
