import { createFileRoute, isRedirect, redirect, useNavigate } from "@tanstack/react-router"
import * as React from "react"
import { Shield, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, extractErrorDetail, ApiError } from "@/lib/api"
import { fetchCurrentUser } from "@/hooks/use-current-user"

/**
 * 登录页 /login (docs/web-pages-design.md §A1).
 * Left 60% brand area (light gray canvas + minimal shield/grid geometry),
 * right 40% login card on white. No color anywhere — errors use a dark
 * background + light text strip (never red, per the monochrome hard line).
 *
 * Wires the real backend: `POST /api/auth/login` sets the httpOnly access +
 * refresh cookies (backend B1), then we navigate to `?redirect=` or `/`.
 * Already-authenticated visitors are bounced to `/` in `beforeLoad`.
 */
export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === "string" ? search.redirect : undefined,
  }),
  beforeLoad: async ({ context }) => {
    // If a valid access cookie is already present, skip the login page. Using
    // fetchCurrentUser (shared QueryClient) pre-warms the cache so the
    // __authenticated guard below doesn't re-hit /auth/me.
    if (!context.queryClient) return
    try {
      await fetchCurrentUser(context.queryClient)
      throw redirect({ to: "/" })
    } catch (e) {
      if (isRedirect(e)) throw e
      // 401 (or any error) → stay on /login and render the form.
    }
  },
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
  const { redirect: redirectTo } = Route.useSearch()
  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [remember, setRemember] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [submitting, setSubmitting] = React.useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api.post("/auth/login", { username, password })
      const target = redirectTo && redirectTo.startsWith("/") ? redirectTo : "/"
      void navigate({ to: target })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(extractErrorDetail(err.data) ?? "登录失败，请检查账号与密码。")
      } else if (err instanceof ApiError && err.status === 403) {
        setError(extractErrorDetail(err.data) ?? "该账号已被禁用，请联系管理员。")
      } else {
        setError("登录失败，请稍后重试。")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-ink-200 md:flex-row">
      {/* Left: brand area (60%) */}
      <div className="relative hidden w-[60%] flex-col justify-center overflow-hidden px-[10%] md:flex">
        {/* Abstract grid + rotated square shield metaphor */}
        <div
          className="pointer-events-none absolute inset-0 z-0 opacity-10"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-ink-400) 1px, transparent 1px), linear-gradient(90deg, var(--color-ink-400) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
        />
        <div className="pointer-events-none absolute left-1/2 top-1/2 size-96 -translate-x-1/2 -translate-y-1/2 rotate-45 border border-ink-500 opacity-20" />
        <div className="pointer-events-none absolute left-1/2 top-1/2 size-64 -translate-x-1/2 -translate-y-1/2 rotate-45 border border-ink-500 opacity-30" />

        <div className="relative z-10 max-w-lg">
          <Shield className="mb-8 size-16 text-ink-900" strokeWidth={1.5} />
          <h1 className="font-sans text-4xl font-bold leading-tight tracking-tight text-ink-900">
            智行卫士
          </h1>
          <p className="mt-4 border-l-2 border-ink-900 py-1 pl-4 font-sans text-sm font-semibold uppercase tracking-widest text-ink-700">
            流水审查 · 标准化 · 智能报告
          </p>
        </div>
        <div className="absolute bottom-12 left-[10%] z-10 font-mono text-xs opacity-60 text-ink-700">
          系统版本: 2.4.1_build_89
          <br />
          安全等级: OMEGA
        </div>
      </div>

      {/* Right: login card (40%) */}
      <div className="flex w-full flex-col justify-center border-l border-ink-400 bg-ink-100 p-8 md:w-[40%] md:p-16">
        {/* Mobile brand header */}
        <div className="mb-12 flex w-full flex-col items-center md:hidden">
          <Shield className="mb-4 size-12 text-ink-900" strokeWidth={1.5} />
          <h1 className="font-sans text-2xl font-bold text-ink-900">智行卫士</h1>
        </div>

        <div className="w-full max-w-sm">
          <h2 className="mb-8 text-left font-sans text-2xl font-bold text-ink-900">
            安全登录
          </h2>

          <form className="flex flex-col gap-8" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="username" className="sr-only">
                审计专员账号
              </label>
              <Input
                id="username"
                type="text"
                placeholder="审计专员账号"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
              />
            </div>

            <div>
              <label htmlFor="password" className="sr-only">
                密码
              </label>
              <Input
                id="password"
                type="password"
                placeholder="密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
              {error && (
                <p
                  role="alert"
                  className="mt-2 rounded-[var(--radius-DEFAULT)] bg-ink-800 px-3 py-2 font-mono text-xs font-semibold text-ink-100"
                >
                  {error}
                </p>
              )}
            </div>

            <div className="flex items-center justify-between pt-2">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  className="size-4 accent-ink-900"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                <span className="text-sm text-ink-700">记住我</span>
              </label>
              <a
                href="#"
                className="text-sm text-ink-900 underline-offset-4 hover:underline"
              >
                忘记密码
              </a>
            </div>

            <Button
              type="submit"
              size="lg"
              className="mt-2 w-full"
              disabled={submitting}
            >
              {submitting ? "登录中…" : "登录"}
              {!submitting && <ArrowRight className="size-4" />}
            </Button>
          </form>

          <div className="mt-12 w-full border-t border-ink-400 pt-8 text-center">
            <p className="font-sans text-[11px] font-bold uppercase tracking-widest text-ink-600">
              受限访问区域 · 仅限授权人员
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
