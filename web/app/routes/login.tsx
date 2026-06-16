import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import { Eye, EyeOff, LogIn, Loader2 } from "lucide-react"
import { useAuth } from "~/hooks/use-auth"

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError("")
    setLoading(true)

    const form = e.currentTarget
    const username = (form.elements.namedItem("username") as HTMLInputElement).value
    const password = (form.elements.namedItem("password") as HTMLInputElement).value

    try {
      await login(username, password)
      navigate("/dashboard")
    } catch {
      setError("用户名或密码错误")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0A0A0A] p-4">
      {/* Background gradient */}
      <div className="fixed inset-0 bg-[radial-gradient(circle_at_50%_50%,#1e1e1e_0%,#0a0a0a_100%)]" />

      <div className="relative z-10 w-full max-w-[400px] space-y-8">
        {/* Header */}
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary shadow-lg shadow-primary/10">
            <svg className="h-7 w-7 text-[#2d3133]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 21h18" />
              <path d="M5 21V7l7-4 7 4v14" />
              <path d="M9 21v-4h6v4" />
              <path d="M9 10h.01" />
              <path d="M15 10h.01" />
              <path d="M9 14h.01" />
              <path d="M15 14h.01" />
            </svg>
          </div>
          <div className="space-y-1">
            <h1 className="text-xl font-semibold text-[#e5e2e1]">Check-YG Web</h1>
            <p className="text-sm text-[#c4c7c9]">员工-客户金额往来审计系统</p>
          </div>
        </div>

        {/* Login Card */}
        <div className="rounded-xl border border-[#334155]/50 bg-[#141414]/80 p-8 shadow-2xl backdrop-blur-xl">
          <form className="space-y-5" onSubmit={handleSubmit}>
            {/* Username */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-[#c4c7c9]" htmlFor="username">
                用户名
              </label>
              <div className="relative">
                <svg className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#c4c7c9]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <input
                  id="username"
                  name="username"
                  type="text"
                  required
                  placeholder="请输入您的账号"
                  className="w-full rounded-lg border border-[#334155] bg-[#1c1b1b] py-2.5 pl-10 pr-4 text-sm text-[#e5e2e1] placeholder:text-[#c4c7c9]/50 transition-all focus:border-white/50 focus:outline-none focus:ring-0"
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-[#c4c7c9]" htmlFor="password">
                密码
              </label>
              <div className="relative">
                <svg className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#c4c7c9]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="••••••••"
                  className="w-full rounded-lg border border-[#334155] bg-[#1c1b1b] py-2.5 pl-10 pr-10 text-sm text-[#e5e2e1] placeholder:text-[#c4c7c9]/50 transition-all focus:border-white/50 focus:outline-none focus:ring-0"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#c4c7c9] transition-colors hover:text-[#e5e2e1]"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Links */}
            <div className="flex items-center justify-between text-xs">
              <span className="cursor-not-allowed text-[#c4c7c9]/40" title="请联系管理员重置密码">
                忘记密码？
              </span>
              <div className="group relative flex items-center gap-1">
                <span className="cursor-not-allowed text-[#c4c7c9]/40">通过邀请码注册</span>
                <svg className="h-3.5 w-3.5 text-[#c4c7c9]/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4" />
                  <path d="M12 8h.01" />
                </svg>
                <div className="absolute bottom-full right-0 mb-2 hidden whitespace-nowrap rounded border border-[#334155] bg-[#353535] px-2 py-1 text-[10px] text-[#e5e2e1] shadow-xl group-hover:block">
                  联系管理员获取邀请码
                </div>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-lg bg-[#93000a]/20 px-3 py-2 text-xs text-[#ffb4ab]">
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-3 text-sm font-medium text-[#2d3133] transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  验证中...
                </>
              ) : (
                <>
                  登录系统
                  <LogIn className="h-4 w-4" />
                </>
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="space-y-4 text-center">
          <div className="h-px bg-gradient-to-r from-transparent via-[#334155] to-transparent" />
          <div className="space-y-2">
            <div className="flex items-center justify-center gap-4">
              <span className="font-mono text-[11px] uppercase tracking-widest text-[#c4c7c9]/40">
                版本 V1.1.0
              </span>
            </div>
            <p className="text-center text-[10px] leading-relaxed text-[#c4c7c9]/30">
              © 2024 Check-YG Web Audit Enterprise.
              <br />
              所有审计日志均已加密并受监控。
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
