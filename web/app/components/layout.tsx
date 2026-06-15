import { NavLink, Outlet, useNavigate } from "react-router"
import { cn } from "~/lib/utils"
import { useAuth } from "~/hooks/use-auth"
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
import { useState } from "react"

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/tasks", label: "Tasks", icon: ClipboardList },
  { to: "/customers", label: "Customers", icon: Users },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/templates", label: "Templates", icon: FileText },
  { to: "/prompts", label: "Prompts", icon: MessageSquare },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/settings", label: "Settings", icon: Settings },
]

export function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [searchOpen, setSearchOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  function handleLogout() {
    logout()
    navigate("/login")
  }

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Sidebar */}
      <aside className="w-[220px] bg-sidebar flex flex-col border-r border-sidebar-border shrink-0">
        {/* Logo */}
        <div className="p-4 flex items-center gap-3">
          <div className="size-8 bg-primary rounded-lg flex items-center justify-center">
            <svg className="w-5 h-5 text-on-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 21h18M3 10h18M5 6l7-3 7 3M4 10v11M20 10v11M8 14v3M12 14v3M16 14v3" />
            </svg>
          </div>
          <div>
            <div className="text-sm font-semibold text-sidebar-foreground leading-tight">Check-YG</div>
            <div className="text-[10px] text-sidebar-foreground/50 leading-tight">Enterprise Audit</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-2 space-y-0.5 overflow-y-auto scroll-thin">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                )
              }
            >
              <item.icon className="w-4 h-4 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Bottom */}
        <div className="p-2 border-t border-sidebar-border space-y-0.5">
          <button className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors">
            <User className="w-4 h-4" />
            User Profile
          </button>
          <button className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors">
            <Moon className="w-4 h-4" />
            Theme
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Bar */}
        <header className="h-14 border-b border-border flex items-center px-4 gap-4 bg-background shrink-0">
          {/* Search */}
          <div className="flex-1 max-w-md relative">
            {searchOpen ? (
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  autoFocus
                  className="w-full bg-surface-container-low border border-border rounded-lg py-1.5 pl-9 pr-16 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/50"
                  placeholder="搜索审计客户..."
                  onBlur={() => setSearchOpen(false)}
                />
                <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border">
                  Ctrl+K
                </kbd>
              </div>
            ) : (
              <button
                onClick={() => setSearchOpen(true)}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                <Search className="w-4 h-4" />
                <span>搜索审计客户...</span>
                <kbd className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border ml-2">
                  Ctrl+K
                </kbd>
              </button>
            )}
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-2">
            <button className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors relative">
              <Bell className="w-4 h-4" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-destructive rounded-full" />
            </button>
            <button className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
              <Settings className="w-4 h-4" />
            </button>

            {/* User Menu */}
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center gap-2 p-1 pr-2 rounded-lg hover:bg-accent transition-colors"
              >
                <div className="w-7 h-7 rounded-full bg-secondary flex items-center justify-center text-secondary-foreground text-xs font-medium">
                  {user?.username?.[0]?.toUpperCase() || "U"}
                </div>
              </button>
              {userMenuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setUserMenuOpen(false)} />
                  <div className="absolute right-0 top-full mt-1 w-48 bg-popover border border-border rounded-lg shadow-xl z-20 py-1">
                    <div className="px-3 py-2 border-b border-border">
                      <div className="text-sm font-medium text-popover-foreground">{user?.username || "User"}</div>
                      <div className="text-xs text-muted-foreground">{user?.role || "unknown"}</div>
                    </div>
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors"
                    >
                      <LogOut className="w-4 h-4" />
                      退出登录
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto scroll-thin">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
