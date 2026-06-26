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
  type AuditDimensionListItem,
  type AuditDimensionUpdateBody,
  type DimensionSeverity,
  type DimensionStep,
} from "@/lib/api"
import { useCurrentUser } from "@/hooks/use-current-user"
import {
  useAuditDimension,
  useCreateAuditDimension,
  useDeleteAuditDimension,
  useUpdateAuditDimension,
  useAuditDimensions,
} from "@/hooks/use-audit-dimensions"

/**
 * 审查维度 /audit-dimensions (06-26-ai-agent).
 *
 * 全局审查维度管理页（单色对齐 keyword-library 卡片管理范式）:
 * - 维度卡片表格：维度名 / 来源（system|agent 标）/ severity / enabled 开关 / purpose 摘要 / 操作.
 * - admin 可新建/编辑/删除/启停。删 system 维度需 admin（后端校验，前端按 403/409 提示）.
 * - 编辑弹窗：name / purpose / steps（list[{tool,params}] 可增删的步骤行） /
 *   judgment / severity / enabled。steps.tool 限只读工具白名单（select）.
 * - 非 admin 只读列表（能看，不能改）.
 *
 * 维度 = 结构化提示词；新维度沉淀 = 加一行提示词，不改码（PRD §一）.
 * 单色 ink tokens，无 radix。severity 用灰阶+形状双编码（沿用 SeverityBadge 范式）.
 */
export const Route = createFileRoute("/__authenticated/audit-dimensions")({
  component: AuditDimensionsPage,
})

/** steps.tool 白名单——对齐后端只读工具集（PRD §二，create_dimension 限此白名单）. */
const TOOL_WHITELIST = [
  "get_task_summary",
  "query_by_time",
  "query_by_amount",
  "query_by_counterparty",
  "query_burst",
] as const

const SEVERITY_OPTIONS: DimensionSeverity[] = ["high", "medium", "low"]

const SEVERITY_LABEL: Record<DimensionSeverity, string> = {
  high: "高",
  medium: "中",
  low: "低",
}

function AuditDimensionsPage() {
  const { user } = useCurrentUser()
  const isAdmin = user?.role === "admin"

  return (
    <>
      <PageHeader
        title="审查维度"
        description="全局 AI 审查维度：维度 = 结构化提示词，「开始分析」时每个启用维度各跑一次。admin 可管理维度，沉淀新维度零代码。"
      />
      <AuditDimensionsCard isAdmin={isAdmin} />
    </>
  )
}

/** 维度管理：列表 table + 新建/编辑/启停/删除. */
function AuditDimensionsCard({ isAdmin }: { isAdmin: boolean }) {
  const dimsQuery = useAuditDimensions()
  const deleteDim = useDeleteAuditDimension()
  const updateDim = useUpdateAuditDimension()
  const [editing, setEditing] = React.useState<AuditDimensionListItem | null>(null)
  const [creating, setCreating] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const dims = dimsQuery.data ?? []

  async function handleDelete(dim: AuditDimensionListItem) {
    setError(null)
    try {
      await deleteDim.mutateAsync(dim.id)
    } catch (err) {
      setError(extractDetail(err) ?? "删除失败")
    }
  }

  async function handleToggleEnabled(
    dim: AuditDimensionListItem,
    enabled: boolean,
  ) {
    setError(null)
    try {
      await updateDim.mutateAsync({ id: dim.id, body: { enabled } })
    } catch (err) {
      setError(extractDetail(err) ?? "切换失败")
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-sans text-base font-bold text-ink-900">
              审查维度卡片
            </h2>
            <p className="mt-1 text-xs text-ink-600">
              维度 = 维度名 + purpose + steps（调哪些只读工具）+ judgment + severity；
              后端按固定模板拼成 prompt 存库。「开始分析」串行跑所有启用维度。
            </p>
          </div>
          {isAdmin && (
            <Button size="sm" onClick={() => setCreating(true)}>
              新建维度
            </Button>
          )}
        </div>

        {dimsQuery.isLoading && <p className="text-sm text-ink-600">加载中…</p>}
        {dimsQuery.isError && (
          <p className="text-sm text-ink-600">维度加载失败，请稍后重试。</p>
        )}

        {dims.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-ink-400 text-left">
                  <Th>维度名</Th>
                  <Th>来源</Th>
                  <Th>severity</Th>
                  <Th>启用</Th>
                  <Th>purpose</Th>
                  {isAdmin && <Th>操作</Th>}
                </tr>
              </thead>
              <tbody>
                {dims.map((d) => (
                  <tr key={d.id} className="border-b border-ink-300">
                    <Td className="font-medium text-ink-900">{d.name}</Td>
                    <Td>
                      <SourceBadge source={d.source} />
                    </Td>
                    <Td>
                      <SeverityBadge severity={d.severity} />
                    </Td>
                    <Td>
                      <Toggle
                        checked={d.enabled}
                        onCheckedChange={(v) => handleToggleEnabled(d, v)}
                        disabled={!isAdmin}
                        aria-label="启用维度"
                      />
                    </Td>
                    <Td className="max-w-[24rem] text-ink-700">
                      <span className="line-clamp-2">{d.purpose}</span>
                    </Td>
                    {isAdmin && (
                      <Td>
                        <div className="flex gap-2">
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => setEditing(d)}
                          >
                            编辑
                          </Button>
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => handleDelete(d)}
                            disabled={deleteDim.isPending}
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

        {!dimsQuery.isLoading && dims.length === 0 && (
          <p className="text-sm text-ink-600">
            暂无审查维度，{isAdmin ? "点击「新建维度」添加。" : "请联系 admin 添加。"}
          </p>
        )}

        {error && <p className="font-mono text-xs font-bold text-ink-900">{error}</p>}

        {creating && (
          <DimensionDialog mode="create" onClose={() => setCreating(false)} />
        )}
        {editing && (
          <DimensionDialog
            mode="edit"
            initial={editing}
            onClose={() => setEditing(null)}
          />
        )}
      </CardContent>
    </Card>
  )
}

/** 来源标 — system（迁移 seed）/ agent（create_dimension 沉淀草稿）. */
function SourceBadge({ source }: { source: "system" | "agent" }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center justify-center rounded-[var(--radius-DEFAULT)] px-1.5 font-sans text-[11px] font-bold",
        source === "system"
          ? "bg-ink-700 text-ink-100"
          : "bg-ink-200 text-ink-800 border border-ink-400",
      )}
    >
      {source === "system" ? "系统" : "沉淀"}
    </span>
  )
}

/** severity 标 — 灰阶+形状双编码（沿用 analyze.tsx SeverityBadge 范式，单色禁彩色）. */
function SeverityBadge({ severity }: { severity: DimensionSeverity }) {
  const styles: Record<DimensionSeverity, string> = {
    high: "bg-ink-900 text-ink-100 rounded-none",
    medium: "bg-ink-700 text-ink-100 rounded-[var(--radius-DEFAULT)]",
    low: "bg-ink-300 text-ink-700 rounded-[var(--radius-full)]",
  }
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-8 items-center justify-center px-1.5 font-sans text-[11px] font-bold",
        styles[severity],
      )}
    >
      {SEVERITY_LABEL[severity]}
    </span>
  )
}

/** 维度新建/编辑对话框.
 * steps = list[{tool, params}] 可增删的步骤行；tool 限只读工具白名单（select）.
 * params 是自由 JSON 文本（key=value 行也行），后端按 dict 存.
 */
function DimensionDialog({
  mode,
  initial,
  onClose,
}: {
  mode: "create" | "edit"
  initial?: AuditDimensionListItem
  onClose: () => void
}) {
  const createDim = useCreateAuditDimension()
  const updateDim = useUpdateAuditDimension()
  // 编辑模式拉详情（列表项不含 judgment/steps）；新建模式不拉.
  const detailQuery = useAuditDimension(mode === "edit" ? initial?.id ?? null : null)
  const [name, setName] = React.useState(initial?.name ?? "")
  const [purpose, setPurpose] = React.useState(initial?.purpose ?? "")
  const [judgment, setJudgment] = React.useState("")
  const [severity, setSeverity] = React.useState<DimensionSeverity>(
    initial?.severity ?? "medium",
  )
  const [enabled, setEnabled] = React.useState(initial?.enabled ?? true)
  const [steps, setSteps] = React.useState<DimensionStep[]>(
    mode === "create" ? [{ tool: TOOL_WHITELIST[0], params: {} }] : [],
  )
  const [error, setError] = React.useState<string | null>(null)
  const [loaded, setLoaded] = React.useState(mode === "create")

  // 编辑模式：详情拉到后回填 judgment（列表项无 judgment，避免覆盖用户已改的值）.
  React.useEffect(() => {
    if (mode === "edit" && detailQuery.data && !loaded) {
      setJudgment(detailQuery.data.judgment)
      setLoaded(true)
    }
  }, [mode, detailQuery.data, loaded])

  function setStepTool(idx: number, tool: string) {
    setSteps((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, tool } : s)),
    )
  }

  function setStepParams(idx: number, raw: string) {
    const params = parseParams(raw)
    setSteps((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, params } : s)),
    )
  }

  function addStep() {
    setSteps((prev) => [...prev, { tool: TOOL_WHITELIST[0], params: {} }])
  }

  function removeStep(idx: number) {
    setSteps((prev) => prev.filter((_, i) => i !== idx))
  }

  async function handleSave() {
    setError(null)
    const cleanName = name.trim()
    if (!cleanName) {
      setError("维度名称不能为空")
      return
    }
    if (!purpose.trim() || !judgment.trim()) {
      setError("purpose / judgment 不能为空")
      return
    }
    try {
      if (mode === "create") {
        await createDim.mutateAsync({
          name: cleanName,
          purpose: purpose.trim(),
          steps,
          judgment: judgment.trim(),
          severity,
          source: "system",
          enabled,
        })
      } else if (initial) {
        const body: AuditDimensionUpdateBody = {
          name: cleanName,
          purpose: purpose.trim(),
          judgment: judgment.trim(),
          severity,
          enabled,
        }
        await updateDim.mutateAsync({ id: initial.id, body })
      }
      onClose()
    } catch (err) {
      setError(extractDetail(err) ?? "保存失败")
    }
  }

  const pending = createDim.isPending || updateDim.isPending

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{mode === "create" ? "新建审查维度" : "编辑审查维度"}</DialogTitle>
        <DialogClose onOpenChange={(o) => !o && onClose()} />
      </DialogHeader>
      <DialogBody className="max-h-[60vh] overflow-y-auto">
        {!loaded ? (
          <p className="text-sm text-ink-600">加载中…</p>
        ) : (
          <div className="flex flex-col gap-4">
            {mode === "edit" && (
              <p className="rounded-[var(--radius-DEFAULT)] bg-ink-200 p-2 text-[11px] text-ink-700">
                提示：此处改名称/purpose/judgment/severity/启用。steps（调哪些工具）
                暂不支持编辑，需调 steps 请新建维度后删旧。
              </p>
            )}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                  维度名称
                </label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                  severity
                </label>
                <select
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value as DimensionSeverity)}
                  className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-2 font-sans text-sm text-ink-900 focus:border-ink-900 focus:outline-none"
                >
                  {SEVERITY_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {SEVERITY_LABEL[s]}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                purpose（要查什么异常）
              </label>
              <textarea
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                rows={2}
                className="w-full resize-none rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 p-2 text-sm text-ink-900 outline-none focus:border-ink-800"
              />
            </div>

            {mode === "create" && (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                  steps（调哪些只读工具 + 参数）
                </label>
                <div className="flex flex-col gap-2">
                  {steps.map((step, idx) => (
                    <div key={idx} className="flex flex-col gap-1.5 rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 p-2">
                      <div className="flex items-center gap-2">
                        <select
                          value={step.tool}
                          onChange={(e) => setStepTool(idx, e.target.value)}
                          className="flex-1 rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-1.5 font-mono text-xs text-ink-900 focus:border-ink-900 focus:outline-none"
                        >
                          {TOOL_WHITELIST.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </select>
                        <Button
                          variant="tertiary"
                          size="sm"
                          onClick={() => removeStep(idx)}
                          disabled={steps.length === 1}
                        >
                          删除
                        </Button>
                      </div>
                      <input
                        defaultValue={formatParams(step.params)}
                        onChange={(e) => setStepParams(idx, e.target.value)}
                        placeholder='参数，如 hours=22,23,0,1 或 mode=large min=50000'
                        className="w-full rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-2 py-1.5 font-mono text-xs text-ink-900 outline-none focus:border-ink-800"
                      />
                    </div>
                  ))}
                  <Button variant="secondary" size="sm" onClick={addStep} className="self-start">
                    + 添加步骤
                  </Button>
                </div>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                judgment（命中/severity 判定标准）
              </label>
              <textarea
                value={judgment}
                onChange={(e) => setJudgment(e.target.value)}
                rows={3}
                className="w-full resize-none rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 p-2 text-sm text-ink-900 outline-none focus:border-ink-800"
              />
            </div>

            <div className="flex items-center gap-3">
              <label className="text-xs font-bold uppercase tracking-widest text-ink-600">
                启用
              </label>
              <Toggle checked={enabled} onCheckedChange={setEnabled} />
              <span className="text-xs text-ink-700">
                {enabled ? "进入「开始分析」" : "草稿（不跑）"}
              </span>
            </div>
          </div>
        )}
        {error && <p className="mt-4 font-mono text-xs font-bold text-ink-900">{error}</p>}
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

/** 把 params dict 格式化成 key=value 行文本（展示用）. */
function formatParams(params?: Record<string, unknown>): string {
  if (!params) return ""
  return Object.entries(params)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(",") : String(v)}`)
    .join(" ")
}

/** 把 key=value 文本解析回 params dict（value 含逗号 → 数组，纯数字 → number）. */
function parseParams(raw: string): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const part of raw.trim().split(/\s+/)) {
    if (!part) continue
    const eq = part.indexOf("=")
    if (eq <= 0) continue
    const k = part.slice(0, eq).trim()
    let v: unknown = part.slice(eq + 1).trim()
    if (typeof v === "string" && v.includes(",")) {
      v = v.split(",").map((s) => s.trim()).filter(Boolean)
    } else if (typeof v === "string" && v !== "" && !Number.isNaN(Number(v))) {
      v = Number(v)
    }
    out[k] = v
  }
  return out
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

/** Extract a human-readable error detail from an ApiError or generic error. */
function extractDetail(err: unknown): string | undefined {
  if (err instanceof ApiError) return extractErrorDetail(err.data)
  if (err instanceof Error) return err.message
  return undefined
}
