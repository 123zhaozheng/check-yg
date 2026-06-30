import * as React from "react"
import { Link, useLocation, useNavigate } from "@tanstack/react-router"
import {
  LayoutDashboard,
  ClipboardList,
  Library,
  Layers,
  Settings as SettingsIcon,
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
import { StatusPill } from "@/components/ui/status-pill"
import { api, type TaskItem } from "@/lib/api"
import { queryClient } from "@/lib/query-client"
import { useCurrentUser } from "@/hooks/use-current-user"
import { useTaskList } from "@/hooks/use-tasks"
import { ShieldLogo } from "@/components/icons/shield-logo"

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
  { to: "/audit-dimensions", label: "审查维度", icon: Layers },
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

  // Topbar 全局搜索：受控 input + 300ms debounce（复用 tasks/index.tsx 模式），
  // 非空时全状态搜（不传 status_filter），下拉最多 8 条命中（任务名/员工名/工号 OR）.
  const [searchQ, setSearchQ] = React.useState("")
  const [debouncedQ, setDebouncedQ] = React.useState("")
  const [panelOpen, setPanelOpen] = React.useState(false)
  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(searchQ), 300)
    return () => clearTimeout(t)
  }, [searchQ])

  const searchEnabled = debouncedQ.trim().length > 0
  const searchQuery = useTaskList({
    search: debouncedQ || undefined,
    page: 1,
    page_size: 8,
    archived: false,
  })
  const searchResults = searchEnabled
    ? searchQuery.data?.items ?? []
    : []

  function handleSelectTask(taskId: number) {
    setSearchQ("")
    setDebouncedQ("")
    setPanelOpen(false)
    void navigate({ to: "/tasks/$id", params: { id: String(taskId) } })
  }

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
            <ShieldLogo className="size-4 text-ink-100" />
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
                value={searchQ}
                onChange={(e) => {
                  setSearchQ(e.target.value)
                  setPanelOpen(true)
                }}
                onFocus={() => setPanelOpen(true)}
                onBlur={() => {
                  // 延迟关闭，让点击候选行先触发跳转.
                  setTimeout(() => setPanelOpen(false), 150)
                }}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setPanelOpen(false)
                    ;(e.target as HTMLInputElement).blur()
                  }
                }}
                placeholder="搜索任务名 / 员工标识…"
                className="h-8 w-64 rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 pl-8 pr-3 text-sm text-ink-900 placeholder:text-ink-600 focus:border-ink-900 focus:outline-none"
              />
              {panelOpen && searchEnabled && (
                <SearchPanel
                  loading={searchQuery.isLoading || searchQuery.isFetching}
                  isError={searchQuery.isError}
                  items={searchResults}
                  onSelect={handleSelectTask}
                />
              )}
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

/**
 * 全局搜索下拉候选面板。
 *
 * 绝对定位在 input 下方，每条「任务名 · 员工名/工号 · 阶段胶囊」，最多 8 条；
 * 点击跳转 /tasks/:id。加载中显示「搜索中…」，无结果显示「无匹配任务」.
 * 全状态搜索（不限 status），后端 search 走 title/employee_name/employee_id OR.
 */
function SearchPanel({
  loading,
  isError,
  items,
  onSelect,
}: {
  loading: boolean
  isError: boolean
  items: TaskItem[]
  onSelect: (taskId: number) => void
}) {
  return (
    <div
      // 阻止 mousedown 关闭面板导致 input onBlur 抢先触发（候选行点击先于失焦）.
      onMouseDown={(e) => e.preventDefault()}
      className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 shadow-[var(--shadow-popover)]"
    >
      {loading ? (
        <div className="px-3 py-3 text-sm text-ink-600">搜索中…</div>
      ) : isError ? (
        <div className="px-3 py-3 text-sm text-ink-800">搜索失败，请重试。</div>
      ) : items.length === 0 ? (
        <div className="px-3 py-3 text-sm text-ink-600">无匹配任务</div>
      ) : (
        <ul className="max-h-80 overflow-y-auto">
          {items.map((task) => {
            return (
              <li key={task.id}>
                <button
                  type="button"
                  // 候选行优先用 mousedown 触发跳转，规避 input onBlur 延迟关闭.
                  onMouseDown={(e) => {
                    e.preventDefault()
                    onSelect(task.id)
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-ink-300"
                >
                  <span className="min-w-0 flex-1 truncate font-sans text-sm text-ink-900">
                    {task.title}
                  </span>
                  {(task.employee_name || task.employee_id) && (
                    <span className="hidden shrink-0 font-mono text-xs text-ink-600 sm:inline">
                      {task.employee_name ?? task.employee_id}
                    </span>
                  )}
                  <StatusPill tone={stageLabelToTone(task.stage)} className="shrink-0">
                    {task.stage}
                  </StatusPill>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

/**
 * 后端 stage label → 灰阶胶囊 tone（与 tasks/index.tsx 的 stageLabelToTone 一致）.
 * stage label 来自后端 _derive_stage_label（单一真相源），不再按 task.status 推。
 * 复刻本地一份避免跨页面耦合；色调对齐设计规范.
 */
function stageLabelToTone(
  stage: string,
): "pending" | "in-progress" | "done" | "reported" | "failed" {
  switch (stage) {
    case "已完成":
    case "清洗完成":
      return "done"
    case "报告生成":
      return "reported"
    case "清洗中":
    case "分析中":
      return "in-progress"
    case "失败":
      return "failed"
    case "待导入":
    case "已暂停":
    case "已取消":
    default:
      return "pending"
  }
}
