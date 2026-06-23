import * as React from "react"
import { createFileRoute } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Toggle } from "@/components/ui/toggle"
import { cn } from "@/lib/utils"
import { ApiError, extractErrorDetail, type SettingSchemaItem, type SettingType } from "@/lib/api"
import { useCurrentUser } from "@/hooks/use-current-user"
import {
  useChangePassword,
  useSettingsSchema,
  useUpdateMe,
  useUpdateSetting,
} from "@/hooks/use-settings"

/**
 * 设置 /settings (docs §D1).
 *
 * Monochrome 4 Tab 设置页（单色原则，安静的页）:
 * - 账户 Tab: 个人信息 (username/email → PATCH users/me) + 改密码
 *   (旧/新/确认 → POST change-password) + 登录设备 (占位静态列表).
 * - 审查参数 / 渠道与解析 / 集成与模型 Tab: 从 GET settings/schema 渲染统一
 *   表单（按 type: string→input / number→input type=number / boolean→toggle
 *   / select→select），分组卡片，每组「保存」主按钮 → PUT settings/{key}.
 *
 * 统一表单组件基于 schema 元数据渲染；分组标题字重建立层级（单色）.
 */
export const Route = createFileRoute("/__authenticated/settings")({
  component: SettingsPage,
})

type TabKey = "account" | "audit" | "channel" | "integration"

const TABS: { key: TabKey; label: string; category: string }[] = [
  { key: "account", label: "账户", category: "account" },
  { key: "audit", label: "审查参数", category: "audit" },
  { key: "channel", label: "渠道与解析", category: "channel" },
  { key: "integration", label: "集成与模型", category: "integration" },
]

function SettingsPage() {
  const [tab, setTab] = React.useState<TabKey>("account")

  return (
    <>
      <PageHeader
        title="设置"
        description="系统级配置：账户、审查参数、渠道与解析、集成与模型。"
      />

      {/* Tab bar */}
      <div className="mb-4 flex space-x-1 border-b border-ink-400">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "px-4 py-2 font-sans text-sm transition-colors",
              tab === t.key
                ? "border-b-2 border-ink-900 font-bold text-ink-900"
                : "border-b-2 border-transparent text-ink-700 hover:text-ink-900",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "account" && <AccountTab />}
      {tab === "audit" && <SchemaTab category="audit" />}
      {tab === "channel" && <SchemaTab category="channel" />}
      {tab === "integration" && <SchemaTab category="integration" />}
    </>
  )
}

// ---------------------------------------------------------------------------
// 账户 Tab
// ---------------------------------------------------------------------------

function AccountTab() {
  const { user } = useCurrentUser()
  const updateMe = useUpdateMe()
  const changePassword = useChangePassword()

  const [username, setUsername] = React.useState(user?.username ?? "")
  const [email, setEmail] = React.useState(user?.email ?? "")
  const [meMsg, setMeMsg] = React.useState<string | null>(null)
  const [meError, setMeError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (user) {
      setUsername(user.username)
      setEmail(user.email)
    }
  }, [user])

  async function handleSaveMe() {
    setMeMsg(null)
    setMeError(null)
    const body: Record<string, string> = {}
    if (username && username !== user?.username) body.username = username
    if (email && email !== user?.email) body.email = email
    if (Object.keys(body).length === 0) {
      setMeError("没有需要保存的更改")
      return
    }
    try {
      await updateMe.mutateAsync(body)
      setMeMsg("个人信息已保存")
    } catch (err) {
      setMeError(extractDetail(err) ?? "保存失败")
    }
  }

  // 改密码表单.
  const [oldPwd, setOldPwd] = React.useState("")
  const [newPwd, setNewPwd] = React.useState("")
  const [confirmPwd, setConfirmPwd] = React.useState("")
  const [pwdMsg, setPwdMsg] = React.useState<string | null>(null)
  const [pwdError, setPwdError] = React.useState<string | null>(null)

  async function handleChangePassword() {
    setPwdMsg(null)
    setPwdError(null)
    if (newPwd !== confirmPwd) {
      setPwdError("两次输入的新密码不一致")
      return
    }
    if (newPwd.length < 8) {
      setPwdError("新密码长度不足，至少 8 位")
      return
    }
    try {
      await changePassword.mutateAsync({
        old_password: oldPwd,
        new_password: newPwd,
      })
      setPwdMsg("密码已修改")
      setOldPwd("")
      setNewPwd("")
      setConfirmPwd("")
    } catch (err) {
      setPwdError(extractDetail(err) ?? "修改失败")
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 个人信息 */}
      <Card>
        <CardContent className="flex flex-col gap-4 p-6">
          <div>
            <h2 className="font-sans text-base font-bold text-ink-900">个人信息</h2>
            <p className="mt-1 text-xs text-ink-600">修改你的用户名与邮箱。</p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                用户名
              </label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                邮箱
              </label>
              <Input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={handleSaveMe} disabled={updateMe.isPending} size="sm">
              {updateMe.isPending ? "保存中…" : "保存"}
            </Button>
            {meMsg && <span className="font-mono text-xs text-ink-700">{meMsg}</span>}
            {meError && (
              <span className="font-mono text-xs font-bold text-ink-900">{meError}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 改密码 */}
      <Card>
        <CardContent className="flex flex-col gap-4 p-6">
          <div>
            <h2 className="font-sans text-base font-bold text-ink-900">修改密码</h2>
            <p className="mt-1 text-xs text-ink-600">新密码至少 8 位。</p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                旧密码
              </label>
              <Input
                type="password"
                value={oldPwd}
                onChange={(e) => setOldPwd(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                新密码
              </label>
              <Input
                type="password"
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                确认新密码
              </label>
              <Input
                type="password"
                value={confirmPwd}
                onChange={(e) => setConfirmPwd(e.target.value)}
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              onClick={handleChangePassword}
              disabled={changePassword.isPending}
              size="sm"
            >
              {changePassword.isPending ? "修改中…" : "修改密码"}
            </Button>
            {pwdMsg && <span className="font-mono text-xs text-ink-700">{pwdMsg}</span>}
            {pwdError && (
              <span className="font-mono text-xs font-bold text-ink-900">{pwdError}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 登录设备（占位静态） */}
      <Card>
        <CardContent className="p-6">
          <h2 className="font-sans text-base font-bold text-ink-900">登录设备</h2>
          <p className="mt-1 text-xs text-ink-600">
            当前活跃会话占位列表（本轮静态展示，后续接入真实设备管理）。
          </p>
          <ul className="mt-4 divide-y divide-ink-300 text-sm">
            <li className="flex items-center justify-between py-3">
              <div>
                <p className="font-medium text-ink-900">当前浏览器</p>
                <p className="font-mono text-xs text-ink-600">本次会话 · 活跃中</p>
              </div>
              <span className="rounded-[var(--radius-DEFAULT)] bg-ink-900 px-2 py-0.5 font-mono text-xs text-ink-100">
                当前
              </span>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Schema-driven Tab（审查参数 / 渠道与解析 / 集成与模型）
// ---------------------------------------------------------------------------

/** MinerU + extraction concurrency 归到「渠道与解析」Tab. */
const CATEGORY_ALIASES: Record<TabKey, string[]> = {
  account: [],
  audit: ["audit"],
  channel: ["channel", "mineru", "extraction"],
  integration: ["llm"],
}

function SchemaTab({ category }: { category: TabKey }) {
  const schemaQuery = useSettingsSchema()
  const updateSetting = useUpdateSetting()

  const items = React.useMemo(() => {
    const all = schemaQuery.data ?? []
    const want = CATEGORY_ALIASES[category]
    return all.filter((item) => want.includes(item.category))
  }, [schemaQuery.data, category])

  if (schemaQuery.isLoading) {
    return (
      <Card>
        <CardContent className="p-10 text-center text-sm text-ink-600">
          加载中…
        </CardContent>
      </Card>
    )
  }
  if (schemaQuery.isError) {
    return (
      <Card>
        <CardContent className="p-10 text-center text-sm text-ink-600">
          设置项加载失败，请稍后重试。
        </CardContent>
      </Card>
    )
  }
  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="p-10 text-center text-sm text-ink-600">
          该分组暂无可配置项。
        </CardContent>
      </Card>
    )
  }

  return (
    <SchemaSettingCard
      items={items}
      updateSetting={updateSetting}
      isPending={updateSetting.isPending}
    />
  )
}

/** 一组 schema 设置项的分组卡片（每组「保存」主按钮 → PUT settings/{key}）. */
function SchemaSettingCard({
  items,
  updateSetting,
  isPending,
}: {
  items: SettingSchemaItem[]
  updateSetting: ReturnType<typeof useUpdateSetting>
  isPending: boolean
}) {
  // 本地编辑态：key → value（string 形式，与后端 Setting.value 一致）.
  const [drafts, setDrafts] = React.useState<Record<string, string>>({})
  const [msg, setMsg] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    const init: Record<string, string> = {}
    for (const item of items) {
      init[item.key] = item.value
    }
    setDrafts(init)
  }, [items])

  function setDraft(key: string, value: string) {
    setDrafts((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSave() {
    setMsg(null)
    setError(null)
    const changed = items.filter((item) => drafts[item.key] !== item.value)
    if (changed.length === 0) {
      setError("没有需要保存的更改")
      return
    }
    try {
      // 逐项 PUT（后端 PUT /settings/{key} 单项更新）.
      for (const item of changed) {
        await updateSetting.mutateAsync({
          key: item.key,
          value: drafts[item.key] ?? "",
        })
      }
      setMsg(`已保存 ${changed.length} 项更改`)
    } catch (err) {
      setError(extractDetail(err) ?? "保存失败")
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {items.map((item) => (
            <SchemaField
              key={item.key}
              item={item}
              value={drafts[item.key] ?? item.value}
              onChange={(v) => setDraft(item.key, v)}
            />
          ))}
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={handleSave} disabled={isPending} size="sm">
            {isPending ? "保存中…" : "保存"}
          </Button>
          {msg && <span className="font-mono text-xs text-ink-700">{msg}</span>}
          {error && (
            <span className="font-mono text-xs font-bold text-ink-900">{error}</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/** 按 schema.type 渲染单个设置字段（input / number / toggle / select）. */
function SchemaField({
  item,
  value,
  onChange,
}: {
  item: SettingSchemaItem
  value: string
  onChange: (value: string) => void
}) {
  const type: SettingType = item.type
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {item.label}
      </label>
      {type === "boolean" ? (
        <div className="flex items-center gap-2 py-1.5">
          <Toggle
            checked={value === "true"}
            onCheckedChange={(checked) => onChange(checked ? "true" : "false")}
            aria-label={item.label}
          />
          <span className="font-mono text-xs text-ink-700">
            {value === "true" ? "启用" : "停用"}
          </span>
        </div>
      ) : type === "select" ? (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-2 font-sans text-sm text-ink-900 focus:border-ink-900 focus:outline-none"
        >
          {(item.options ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : (
        <Input
          type={type === "number" ? "number" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {item.description && (
        <p className="text-[11px] text-ink-600">{item.description}</p>
      )}
    </div>
  )
}

/** Extract a human-readable error detail from an ApiError or generic error. */
function extractDetail(err: unknown): string | undefined {
  if (err instanceof ApiError) return extractErrorDetail(err.data)
  if (err instanceof Error) return err.message
  return undefined
}
