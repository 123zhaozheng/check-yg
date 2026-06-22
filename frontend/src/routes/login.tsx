import { createFileRoute, useNavigate } from "@tanstack/react-router"
import * as React from "react"
import { Shield, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/**
 * 登录页 /login (docs/web-pages-design.md §A1).
 * Left 60% brand area (light gray canvas + minimal shield/grid geometry),
 * right 40% login card on white. No color anywhere — errors use bold dark text.
 * Placeholder only — S1 login slice wires the real /api/auth/login call.
 */
export const Route = createFileRoute("/login")({
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
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
      // Placeholder: real auth wired in S1 (POST /api/auth/login with cookie).
      await new Promise((r) => setTimeout(r, 300))
      void navigate({ to: "/" })
    } catch {
      setError("登录失败，请检查账号与密码。")
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
                <p className="mt-2 font-mono text-xs font-semibold text-ink-900">
                  错误：{error}
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
              登录
              <ArrowRight className="size-4" />
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
