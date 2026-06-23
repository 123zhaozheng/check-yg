import * as React from "react"
import { Link, useLocation, useNavigate } from "@tanstack/react-router"
import {
  LayoutDashboard,
  ClipboardList,
  Library,
  Settings as SettingsIcon,
  Shield,
  Search,
  Bell,
  HelpCircle,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { api } from "@/lib/api"
import { queryClient } from "@/lib/query-client"
import { useCurrentUser } from "@/hooks/use-current-user"

/**
 * Application shell (docs/web-pages-design.md §A2):
 *   sidebar 240px (collapsible to 64px icon-only)
 *   topbar 56px (breadcrumbs + search + notifications/help/avatar)
 *   main canvas #f7f7f8 with white cards
 * Active nav item: 3px black left bar + light gray fill (no color highlight).
 * All labels in Chinese.
 */

const NAV_ITEMS: ReadonlyArray<{
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  exact?: boolean
}> = [
  { to: "/", label: "工作台", icon: LayoutDashboard, exact: true },
  { to: "/tasks", label: "审查任务", icon: ClipboardList },
  { to: "/keyword-library", label: "关键词库", icon: Library },
  { to: "/settings", label: "设置", icon: SettingsIcon },
]

function NavLink({
  to,
  label,
  icon: Icon,
  exact,
  collapsed,
}: {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  exact?: boolean
  collapsed: boolean
}) {
  const location = useLocation()
  const isActive = exact
    ? location.pathname === to
    : location.pathname === to || location.pathname.startsWith(`${to}/`)

  return (
    <Link
      to={to}
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "nav-active-bar flex items-center gap-3 rounded-[var(--radius-DEFAULT)] py-2.5 text-sm transition-colors",
        collapsed ? "justify-center px-0" : "px-3",
        isActive
          ? "bg-ink-300 font-semibold text-ink-900"
          : "text-ink-700 hover:bg-ink-300 hover:text-ink-900",
        !isActive && "before:hidden",
      )}
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = React.useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useCurrentUser()
  const [loggingOut, setLoggingOut] = React.useState(false)

  const sidebarWidth = collapsed ? "w-16" : "w-60"

  // Crude breadcrumb from path — placeholders until real routes carry titles.
  const crumbs = location.pathname
    .split("/")
    .filter(Boolean)
    .map((seg) => decodeURIComponent(seg))

  async function handleLogout() {
    if (loggingOut) return
    setLoggingOut(true)
    try {
      await api.post("/auth/logout")
    } catch {
      // Even if the network call fails, drop local state and bounce to /login.
    } finally {
      queryClient.clear()
      setLoggingOut(false)
      void navigate({ to: "/login", search: { redirect: undefined } })
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-ink-200 text-ink-800">
      {/* Sidebar */}
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-ink-400 bg-ink-100 transition-[width] duration-200",
          sidebarWidth,
        )}
      >
        {/* Brand header */}
        <div
          className={cn(
            "flex h-14 items-center gap-3 border-b border-ink-400",
            collapsed ? "justify-center px-0" : "px-4",
          )}
        >
          <div className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-DEFAULT)] bg-ink-900">
            <Shield className="size-4 text-ink-100" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="truncate text-sm font-bold leading-tight text-ink-900">
                智行卫士
              </div>
              <div className="truncate text-[11px] leading-tight text-ink-600">
                流水审查平台
              </div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav
          className={cn(
            "flex-1 space-y-1 py-4",
            collapsed ? "px-2" : "px-3",
          )}
        >
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              label={item.label}
              icon={item.icon}
              exact={item.exact}
              collapsed={collapsed}
            />
          ))}
        </nav>

        {/* Collapse toggle */}
        <div className="border-t border-ink-400 p-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-center text-ink-700"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
            title={collapsed ? "展开侧栏" : "收起侧栏"}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4" />
            ) : (
              <>
                <PanelLeftClose className="size-4" />
                <span>收起侧栏</span>
              </>
            )}
          </Button>
        </div>

        {/* User profile (bottom) */}
        <div
          className={cn(
            "flex items-center gap-3 border-t border-ink-400 py-4",
            collapsed ? "justify-center px-0" : "px-4",
          )}
        >
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink-300 font-mono text-xs font-semibold text-ink-900">
            {(user?.username ?? "?").slice(0, 1).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-ink-900">
                {user?.username ?? "未登录"}
              </div>
              <div className="truncate font-mono text-[11px] text-ink-600">
                {user?.role ?? "—"}
              </div>
            </div>
          )}
          {!collapsed && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={handleLogout}
              disabled={loggingOut}
              aria-label="退出登录"
              title="退出登录"
              className="text-ink-700 hover:text-ink-900"
            >
              <LogOut className="size-4" />
            </Button>
          )}
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top bar (56px) */}
        <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-ink-400 bg-ink-100 px-6">
          {/* Breadcrumbs */}
          <nav className="flex min-w-0 items-center gap-2 text-sm text-ink-700">
            <span className="text-ink-600">智行卫士</span>
            {crumbs.length > 0 && <Separator orientation="vertical" className="h-3" />}
            {crumbs.map((seg, i) => (
              <React.Fragment key={`${seg}-${i}`}>
                <span
                  className={cn(
                    "truncate",
                    i === crumbs.length - 1
                      ? "font-semibold text-ink-900"
                      : "text-ink-700",
                  )}
                >
                  {seg}
                </span>
                {i < crumbs.length - 1 && (
                  <span className="text-ink-500">/</span>
                )}
              </React.Fragment>
            ))}
          </nav>

          {/* Right actions */}
          <div className="flex items-center gap-2">
            <div className="relative hidden md:block">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-600" />
              <input
                type="text"
                placeholder="搜索任务名 / 员工标识…"
                className="h-8 w-64 rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 pl-8 pr-3 text-sm text-ink-900 placeholder:text-ink-600 focus:border-ink-900 focus:outline-none"
              />
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="通知"
              title="通知"
              className="text-ink-700"
            >
              <Bell className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="帮助"
              title="帮助"
              className="text-ink-700"
            >
              <HelpCircle className="size-4" />
            </Button>
          </div>
        </header>

        {/* Main content — #f7f7f8 canvas */}
        <main className="scroll-thin flex-1 overflow-y-auto bg-ink-200 p-6">
          <div className="mx-auto max-w-[1440px]">{children}</div>
        </main>
      </div>
    </div>
  )
}
