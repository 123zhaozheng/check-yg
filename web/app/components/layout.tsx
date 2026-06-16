import { NavLink, Outlet, useNavigate } from "react-router"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { cn } from "~/lib/utils"
import { useAuth } from "~/hooks/use-auth"
import { useWebSocket } from "~/hooks/use-websocket"
import {
  LayoutDashboard,
  ClipboardList,
  Users,
  BarChart3,
  FileText,
  MessageSquare,
  ScrollText,
  Settings,
  Search,
  Bell,
  User,
  LogOut,
  Moon,
} from "lucide-react"

const navItems = [
  { to: "/dashboard", label: "工作台", icon: LayoutDashboard },
  { to: "/tasks", label: "审查任务", icon: ClipboardList },
  { to: "/customers", label: "客户名单", icon: Users },
  { to: "/analytics", label: "数据分析", icon: BarChart3 },
  { to: "/templates", label: "模板", icon: FileText },
  { to: "/prompts", label: "提示词", icon: MessageSquare },
  { to: "/logs", label: "日志", icon: ScrollText },
  { to: "/settings", label: "设置", icon: Settings },
]

export function Layout() {
  const { user, logout } = useAuth()
  const { status, lastMessage } = useWebSocket("/ws")
  const navigate = useNavigate()
  const [searchOpen, setSearchOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  useEffect(() => {
    if (lastMessage?.type !== "notification" || !lastMessage.payload) {
      return
    }

    const payload = lastMessage.payload as {
      title?: string
      message?: string
    }
    toast(payload.title || "通知", {
      description: payload.message,
    })
  }, [lastMessage])

  function handleLogout() {
    logout()
    navigate("/login")
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: "var(--background)", color: "var(--foreground)" }}>
      {/* Sidebar */}
      <aside
        className="flex w-[220px] shrink-0 flex-col border-r"
        style={{
          backgroundColor: "var(--sidebar)",
          borderColor: "var(--sidebar-border)",
        }}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 p-4">
          <div
            className="flex size-8 items-center justify-center rounded-lg"
            style={{ backgroundColor: "var(--primary)" }}
          >
            <svg className="h-5 w-5" style={{ color: "var(--primary-foreground)" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 21h18M3 10h18M5 6l7-3 7 3M4 10v11M20 10v11M8 14v3M12 14v3M16 14v3" />
            </svg>
          </div>
          <div>
            <div className="text-sm font-semibold leading-tight" style={{ color: "var(--sidebar-foreground)" }}>Check-YG</div>
            <div className="text-[10px] leading-tight" style={{ color: "var(--sidebar-foreground)", opacity: 0.5 }}>Enterprise Audit</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="scroll-thin flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "font-medium"
                    : "hover:opacity-80"
                )
              }
              style={({ isActive }) =>
                isActive
                  ? {
                      backgroundColor: "var(--sidebar-accent)",
                      color: "var(--sidebar-accent-foreground)",
                    }
                  : {
                      color: "var(--sidebar-foreground)",
                      opacity: 0.7,
                    }
              }
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Bottom */}
        <div className="space-y-0.5 border-t p-2" style={{ borderColor: "var(--sidebar-border)" }}>
          <button
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors hover:opacity-80"
            style={{ color: "var(--sidebar-foreground)", opacity: 0.7 }}
            onClick={() => navigate("/settings")}
          >
            <User className="h-4 w-4" />
            用户资料
          </button>
          <button
            className="flex w-full cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm"
            style={{ color: "var(--sidebar-foreground)", opacity: 0.45 }}
            disabled
            title="主题切换暂未接入"
          >
            <Moon className="h-4 w-4" />
            主题
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top Bar */}
        <header
          className="flex h-14 shrink-0 items-center border-b px-4 gap-4"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--background)" }}
        >
          {/* Search */}
          <div className="relative max-w-md flex-1">
            {searchOpen ? (
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" style={{ color: "var(--muted-foreground)" }} />
                <input
                  autoFocus
                  className="w-full rounded-lg border py-1.5 pl-9 pr-16 text-sm focus:outline-none"
                  style={{
                    backgroundColor: "var(--surface-container-low)",
                    borderColor: "var(--border)",
                    color: "var(--foreground)",
                  }}
                  placeholder="搜索审计客户..."
                  onBlur={() => setSearchOpen(false)}
                />
                <kbd
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded border px-1.5 py-0.5 text-[10px]"
                  style={{ color: "var(--muted-foreground)", backgroundColor: "var(--muted)", borderColor: "var(--border)" }}
                >
                  Ctrl+K
                </kbd>
              </div>
            ) : (
              <button
                onClick={() => setSearchOpen(true)}
                className="flex items-center gap-2 text-sm transition-colors hover:opacity-80"
                style={{ color: "var(--muted-foreground)" }}
              >
                <Search className="h-4 w-4" />
                <span>搜索审计客户...</span>
                <kbd
                  className="ml-2 rounded border px-1.5 py-0.5 text-[10px]"
                  style={{ color: "var(--muted-foreground)", backgroundColor: "var(--muted)", borderColor: "var(--border)" }}
                >
                  Ctrl+K
                </kbd>
              </button>
            )}
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-2">
            <button
              className="relative rounded-lg p-2 transition-colors hover:opacity-80"
              style={{ color: "var(--muted-foreground)" }}
              title={`WebSocket: ${status}`}
            >
              <Bell className="h-4 w-4" />
              <span
                className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full"
                style={{
                  backgroundColor:
                    status === "connected"
                      ? "var(--chart-2)"
                      : status === "connecting"
                        ? "var(--chart-4)"
                        : "var(--muted-foreground)",
                }}
              />
            </button>
            <button
              className="rounded-lg p-2 transition-colors hover:opacity-80"
              style={{ color: "var(--muted-foreground)" }}
              onClick={() => navigate("/settings")}
            >
              <Settings className="h-4 w-4" />
            </button>

            {/* User Menu */}
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center gap-2 rounded-lg p-1 pr-2 transition-colors hover:opacity-80"
              >
                <div
                  className="flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium"
                  style={{ backgroundColor: "var(--secondary)", color: "var(--secondary-foreground)" }}
                >
                  {user?.username?.[0]?.toUpperCase() || "U"}
                </div>
              </button>
              {userMenuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setUserMenuOpen(false)} />
                  <div
                    className="absolute right-0 top-full z-20 mt-1 w-48 rounded-lg border py-1 shadow-xl"
                    style={{ backgroundColor: "var(--popover)", borderColor: "var(--border)" }}
                  >
                    <div className="border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
                      <div className="text-sm font-medium" style={{ color: "var(--popover-foreground)" }}>{user?.username || "User"}</div>
                      <div className="text-xs" style={{ color: "var(--muted-foreground)" }}>{user?.role || "unknown"}</div>
                    </div>
                    <button
                      onClick={handleLogout}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors hover:opacity-80"
                      style={{ color: "var(--destructive)" }}
                    >
                      <LogOut className="h-4 w-4" />
                      退出登录
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="scroll-thin flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
