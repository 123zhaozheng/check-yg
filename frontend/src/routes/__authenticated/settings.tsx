import * as React from "react"
import { createFileRoute } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Toggle } from "@/components/ui/toggle"
import { cn } from "@/lib/utils"
import {
  ApiError,
  extractErrorDetail,
  type LLMModel,
  type LLMModelUpsertBody,
  type SettingSchemaItem,
  type SettingType,
  type Stage,
  type ThinkingLevel,
} from "@/lib/api"
import { useCurrentUser } from "@/hooks/use-current-user"
import {
  useChangePassword,
  useSettingsSchema,
  useUpdateMe,
  useUpdateSetting,
} from "@/hooks/use-settings"
import {
  useCreateLLMModel,
  useDeleteLLMModel,
  useLLMModelAssignments,
  useLLMModels,
  useUpdateLLMModel,
  useUpsertLLMModelAssignment,
} from "@/hooks/use-llm-models"

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
      <PageHeader title="设置" />

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
      {tab === "integration" && <IntegrationTab />}
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

// ---------------------------------------------------------------------------
// 集成与模型 Tab — 模型卡片管理 + 阶段指派 + llm.* 兜底配置（06-23-llm-model-card）
// ---------------------------------------------------------------------------

const STAGE_LABELS: { stage: Stage; label: string }[] = [
  { stage: "classification", label: "分类" },
  { stage: "portrait", label: "画像" },
  { stage: "normalization", label: "标准化" },
  { stage: "ai_analysis", label: "AI 分析" },
  { stage: "ai_qa", label: "AI 问答" },
  { stage: "report_generation", label: "报告生成" },
  { stage: "keyword_generation", label: "关键词生成" },
]

const THINKING_OPTIONS: ThinkingLevel[] = ["off", "low", "medium", "high"]

const THINKING_LABELS: Record<ThinkingLevel, string> = {
  off: "关闭",
  low: "低",
  medium: "中",
  high: "高",
}

const EMPTY_CARD: LLMModelUpsertBody = {
  display_name: "",
  model_name: "",
  provider_base_url: "",
  api_key: "",
  context_length: 0,
  max_output: 0,
  supports_tool_call: true,
  supports_tool_choice_required: true,
  is_reasoning: false,
  supports_streaming: true,
  default_thinking: "off",
  default_max_tokens: 4000,
  default_temperature: null,
}

function IntegrationTab() {
  const { user } = useCurrentUser()
  const isAdmin = user?.role === "admin"

  return (
    <div className="flex flex-col gap-4">
      <ModelCardsCard isAdmin={isAdmin} />
      <StageAssignmentCard isAdmin={isAdmin} />
    </div>
  )
}

/** 模型卡片管理：列表 table + 新建/编辑/删除. */
function ModelCardsCard({ isAdmin }: { isAdmin: boolean }) {
  const modelsQuery = useLLMModels()
  const deleteModel = useDeleteLLMModel()
  const [editing, setEditing] = React.useState<LLMModel | null>(null)
  const [creating, setCreating] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const models = modelsQuery.data ?? []

  async function handleDelete(model: LLMModel) {
    setError(null)
    try {
      await deleteModel.mutateAsync({ id: model.id })
    } catch (err) {
      const detail = extractDetail(err)
      // 409 = 被阶段指派：弹确认框，一键解除指派并删除（force=true）。
      if (err instanceof ApiError && err.status === 409) {
        const ok = window.confirm(
          `${detail ?? "该卡片被阶段指派"}\n\n是否解除所有指派并删除该卡片？`,
        )
        if (ok) {
          try {
            await deleteModel.mutateAsync({ id: model.id, force: true })
            return
          } catch (err2) {
            setError(extractDetail(err2) ?? "删除失败")
            return
          }
        }
        return
      }
      setError(detail ?? "删除失败")
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-sans text-base font-bold text-ink-900">模型卡片</h2>
            <p className="mt-1 text-xs text-ink-600">
              管理 LLM 连接与模型元信息（上下文 / 最大输出 / 工具调用 / 推理模式 /
              流式）。api_key 脱敏显示，编辑留空不改。
            </p>
          </div>
          {isAdmin && (
            <Button size="sm" onClick={() => setCreating(true)}>
              新建卡片
            </Button>
          )}
        </div>

        {modelsQuery.isLoading && (
          <p className="text-sm text-ink-600">加载中…</p>
        )}
        {modelsQuery.isError && (
          <p className="text-sm text-ink-600">模型卡片加载失败，请稍后重试。</p>
        )}

        {models.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-ink-400 text-left">
                  <Th>显示名</Th>
                  <Th>model</Th>
                  <Th>上下文</Th>
                  <Th>最大输出</Th>
                  <Th>工具调用</Th>
                  <Th>推理模式</Th>
                  <Th>流式</Th>
                  <Th>max_tokens</Th>
                  <Th>thinking</Th>
                  {isAdmin && <Th>操作</Th>}
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.id} className="border-b border-ink-300">
                    <Td className="font-medium text-ink-900">{m.display_name}</Td>
                    <Td className="font-mono text-xs">{m.model_name}</Td>
                    <Td className="font-mono text-xs">{formatTokens(m.context_length)}</Td>
                    <Td className="font-mono text-xs">{formatTokens(m.max_output)}</Td>
                    <Td>{m.supports_tool_call ? "是" : "否"}</Td>
                    <Td>{m.is_reasoning ? "是" : "否"}</Td>
                    <Td>{m.supports_streaming ? "是" : "否"}</Td>
                    <Td className="font-mono text-xs">{m.default_max_tokens}</Td>
                    <Td>{THINKING_LABELS[m.default_thinking]}</Td>
                    {isAdmin && (
                      <Td>
                        <div className="flex gap-2">
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => setEditing(m)}
                          >
                            编辑
                          </Button>
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => handleDelete(m)}
                            disabled={deleteModel.isPending}
                          >
                            删除
                          </Button>
                        </div>
                      </Td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!modelsQuery.isLoading && models.length === 0 && (
          <p className="text-sm text-ink-600">暂无模型卡片，点击「新建卡片」添加。</p>
        )}

        {error && (
          <p className="font-mono text-xs font-bold text-ink-900">{error}</p>
        )}

        {creating && (
          <ModelCardDialog
            mode="create"
            onClose={() => setCreating(false)}
          />
        )}
        {editing && (
          <ModelCardDialog
            mode="edit"
            initial={editing}
            onClose={() => setEditing(null)}
          />
        )}
      </CardContent>
    </Card>
  )
}

/** 阶段模型指派：6 阶段各一个下拉，选卡片或「未指派（用兜底）」. */
function StageAssignmentCard({ isAdmin }: { isAdmin: boolean }) {
  const assignmentsQuery = useLLMModelAssignments()
  const modelsQuery = useLLMModels()
  const upsert = useUpsertLLMModelAssignment()
  const [error, setError] = React.useState<string | null>(null)

  const assignments = assignmentsQuery.data ?? []
  const models = modelsQuery.data ?? []

  async function handleAssign(stage: Stage, modelId: number | null) {
    setError(null)
    try {
      await upsert.mutateAsync({ stage, body: { llm_model_id: modelId } })
    } catch (err) {
      setError(extractDetail(err) ?? "指派失败")
    }
  }

  if (assignmentsQuery.isLoading || modelsQuery.isLoading) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-ink-600">加载中…</CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div>
          <h2 className="font-sans text-base font-bold text-ink-900">阶段模型指派</h2>
          <p className="mt-1 text-xs text-ink-600">
            为每个阶段指定一张模型卡片；未指派时回退「集成与模型」兜底配置 +
            模块默认值。
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {STAGE_LABELS.map(({ stage, label }) => {
            const assignment = assignments.find((a) => a.stage === stage)
            const value = assignment?.llm_model_id ?? ""
            return (
              <div key={stage} className="flex flex-col gap-1">
                <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                  {label}
                </label>
                <select
                  value={value}
                  disabled={!isAdmin}
                  onChange={(e) =>
                    handleAssign(stage, e.target.value === "" ? null : Number(e.target.value))
                  }
                  className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-2 font-sans text-sm text-ink-900 focus:border-ink-900 focus:outline-none disabled:opacity-60"
                >
                  <option value="">未指派（用兜底）</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.display_name}（{m.model_name}）
                    </option>
                  ))}
                </select>
                {assignment?.llm_model && (
                  <p className="text-[11px] text-ink-600">
                    当前：{assignment.llm_model.display_name} · max_tokens=
                    {assignment.llm_model.default_max_tokens} · thinking=
                    {THINKING_LABELS[assignment.llm_model.default_thinking]}
                    {assignment.llm_model.is_reasoning ? " · 推理模型" : ""}
                  </p>
                )}
              </div>
            )
          })}
        </div>

        {error && (
          <p className="font-mono text-xs font-bold text-ink-900">{error}</p>
        )}
      </CardContent>
    </Card>
  )
}

/** 模型卡片新建/编辑对话框. */
function ModelCardDialog({
  mode,
  initial,
  onClose,
}: {
  mode: "create" | "edit"
  initial?: LLMModel
  onClose: () => void
}) {
  const createModel = useCreateLLMModel()
  const updateModel = useUpdateLLMModel()
  const [form, setForm] = React.useState<LLMModelUpsertBody>(() =>
    initial
      ? {
          display_name: initial.display_name,
          model_name: initial.model_name,
          provider_base_url: initial.provider_base_url,
          api_key: "",
          context_length: initial.context_length,
          max_output: initial.max_output,
          supports_tool_call: initial.supports_tool_call,
          supports_tool_choice_required: initial.supports_tool_choice_required,
          is_reasoning: initial.is_reasoning,
          supports_streaming: initial.supports_streaming,
          default_thinking: initial.default_thinking,
          default_max_tokens: initial.default_max_tokens,
          default_temperature: initial.default_temperature ?? null,
        }
      : { ...EMPTY_CARD },
  )
  const [error, setError] = React.useState<string | null>(null)

  function setField<K extends keyof LLMModelUpsertBody>(
    key: K,
    value: LLMModelUpsertBody[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSave() {
    setError(null)
    try {
      if (mode === "create") {
        await createModel.mutateAsync(form)
      } else if (initial) {
        await updateModel.mutateAsync({ id: initial.id, body: form })
      }
      onClose()
    } catch (err) {
      setError(extractDetail(err) ?? "保存失败")
    }
  }

  const pending = createModel.isPending || updateModel.isPending

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{mode === "create" ? "新建模型卡片" : "编辑模型卡片"}</DialogTitle>
        <DialogClose onOpenChange={(o) => !o && onClose()} />
      </DialogHeader>
      <DialogBody className="max-h-[60vh] overflow-y-auto">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FieldText
            label="显示名"
            value={form.display_name}
            onChange={(v) => setField("display_name", v)}
          />
          <FieldText
            label="模型 model id"
            value={form.model_name}
            onChange={(v) => setField("model_name", v)}
          />
          <FieldText
            label="端点 base_url"
            value={form.provider_base_url}
            onChange={(v) => setField("provider_base_url", v)}
            full
          />
          <FieldText
            label="API Key（留空不改）"
            value={form.api_key ?? ""}
            onChange={(v) => setField("api_key", v)}
            full
            placeholder={mode === "edit" ? "********（留空不改原值）" : "sk-..."}
          />
          <FieldNumber
            label="上下文长度"
            value={form.context_length}
            onChange={(v) => setField("context_length", Number(v) || 0)}
          />
          <FieldNumber
            label="最大输出"
            value={form.max_output}
            onChange={(v) => setField("max_output", Number(v) || 0)}
          />
          <FieldNumber
            label="默认 max_tokens"
            value={form.default_max_tokens}
            onChange={(v) => setField("default_max_tokens", Number(v) || 0)}
          />
          <div className="flex flex-col gap-1">
            <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
              默认 thinking
            </label>
            <select
              value={form.default_thinking}
              onChange={(e) => setField("default_thinking", e.target.value as ThinkingLevel)}
              className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-2 font-sans text-sm text-ink-900 focus:border-ink-900 focus:outline-none"
            >
              {THINKING_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {THINKING_LABELS[t]}
                </option>
              ))}
            </select>
          </div>
          <FieldNumber
            label="默认 temperature（空=兜底）"
            value={form.default_temperature ?? ""}
            onChange={(v) => setField("default_temperature", v === "" ? null : v)}
            allowEmpty
          />
          <div className="col-span-full grid grid-cols-2 gap-3 sm:grid-cols-4">
            <ToggleField
              label="工具调用"
              checked={form.supports_tool_call}
              onChange={(v) => setField("supports_tool_call", v)}
            />
            <ToggleField
              label="tool_choice:required"
              checked={form.supports_tool_choice_required}
              onChange={(v) => setField("supports_tool_choice_required", v)}
            />
            <ToggleField
              label="推理模型"
              checked={form.is_reasoning}
              onChange={(v) => setField("is_reasoning", v)}
            />
            <ToggleField
              label="流式"
              checked={form.supports_streaming}
              onChange={(v) => setField("supports_streaming", v)}
            />
          </div>
        </div>
        {error && (
          <p className="mt-4 font-mono text-xs font-bold text-ink-900">{error}</p>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="tertiary" onClick={onClose}>
          取消
        </Button>
        <Button onClick={handleSave} disabled={pending}>
          {pending ? "保存中…" : "保存"}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-2 py-2 text-xs font-bold uppercase tracking-widest text-ink-600">
      {children}
    </th>
  )
}

function Td({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return <td className={cn("px-2 py-2 text-ink-900", className)}>{children}</td>
}

function FieldText({
  label,
  value,
  onChange,
  full,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  full?: boolean
  placeholder?: string
}) {
  return (
    <div className={cn("flex flex-col gap-1", full && "sm:col-span-2")}>
      <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </label>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}

function FieldNumber({
  label,
  value,
  onChange,
  allowEmpty,
}: {
  label: string
  value: number | ""
  onChange: (v: number | "") => void
  allowEmpty?: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </label>
      <Input
        type="number"
        value={value}
        onChange={(e) => {
          if (allowEmpty && e.target.value === "") {
            onChange("")
            return
          }
          const n = Number(e.target.value)
          onChange(Number.isNaN(n) ? (allowEmpty ? "" : 0) : n)
        }}
      />
    </div>
  )
}

function ToggleField({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      <Toggle
        checked={checked}
        onCheckedChange={onChange}
        aria-label={label}
      />
      <span className="font-mono text-xs text-ink-700">
        {label}：{checked ? "启用" : "停用"}
      </span>
    </div>
  )
}

function formatTokens(n: number): string {
  if (n <= 0) return "—"
  if (n >= 1000) return `${(n / 1000).toLocaleString()}K`
  return String(n)
}
