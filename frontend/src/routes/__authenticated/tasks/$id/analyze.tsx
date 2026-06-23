import * as React from "react"
import { createFileRoute, useParams } from "@tanstack/react-router"
import { Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { FindingItem, Severity } from "@/lib/api"
import {
  useChatAnalyze,
  useFindings,
  usePatchFinding,
  useStartAnalysis,
} from "@/hooks/use-analysis"
import { useTask } from "@/hooks/use-tasks"

/**
 * AI 分析 /tasks/:id/analyze (docs §C4).
 *
 * Monochrome AI analysis page (无 stitch 源稿，按 prd + docs §C4 自创，单色):
 * - Header: 面包屑 + "AI 分析" + 副标题.
 * - 分析控制条: 开始分析黑底主按钮 + 快速/深度描边单选(segmented) +
 *   上次分析时间灰文 + 模型参数灰文.
 * - 分析中: 灰阶进度条 + 阶段文字（占位快速完成）.
 * - 左侧异常发现列表 (w-96): 按 severity 降序，severity 灰阶+形状双编码
 *   (高=黑底白字方块 bg-ink-900 text-ink-100 / 中=深灰 bg-ink-700 text-ink-100
 *   / 低=浅灰 bg-ink-300 text-ink-700)，选中项 border-l-2 border-ink-900 +
 *   bg-ink-300. 每项显 severity 标 + description 摘要 + confidence.
 * - 右侧异常详情: AI 推理摘要 + 关联记录列表（占位）+ 时间分布黑白灰小 bar
 *   + 置信度灰阶水平条 (bg-ink-200 底 bg-ink-900 填充) + 三按钮
 *   (采纳为告警/忽略/添加备注 → PATCH).
 * - 底部多轮对话区: 气泡 (AI bg-ink-200 text-ink-900 / 用户 bg-ink-900
 *   text-ink-100) + 输入框 + 发送 → POST chat → 占位回复追加.
 * - TanStack Query 拉 findings，mutation 跑 analyze/patch/chat.
 *
 * agent 接入点结构遵循 docs/research/pydantic-ai-conventions.md (v1.107.0)
 * （后端 app/llm/analysis.py：AuditDeps + @agent.tool + ModelMessagesTypeAdapter
 * + message_history）。本切片 agent.run/chat 走占位实现。
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/analyze")({
  component: AnalyzePage,
})

type AnalysisMode = "quick" | "deep"

function AnalyzePage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/analyze" })
  const taskId = Number(id)

  const [mode, setMode] = React.useState<AnalysisMode>("quick")
  const [selectedId, setSelectedId] = React.useState<number | null>(null)
  const [progressStage, setProgressStage] = React.useState<string | null>(null)

  const findingsQuery = useFindings(taskId)
  const taskQuery = useTask(taskId)
  const startAnalysis = useStartAnalysis(taskId)
  const patchFinding = usePatchFinding(taskId)
  const chatAnalyze = useChatAnalyze(taskId)

  const findings = findingsQuery.data?.items ?? []
  const lastAnalysisAt = (taskQuery.data?.config as
    | { last_analysis_at?: string }
    | undefined)?.last_analysis_at

  // Auto-select the first finding when the list loads or changes.
  React.useEffect(() => {
    if (findings.length > 0 && !findings.some((f) => f.id === selectedId)) {
      setSelectedId(findings[0].id)
    }
    if (findings.length === 0) {
      setSelectedId(null)
    }
  }, [findings, selectedId])

  const selected = findings.find((f) => f.id === selectedId) ?? null

  async function handleAnalyze() {
    setProgressStage("正在分析…")
    try {
      await startAnalysis.mutateAsync(mode)
    } finally {
      // 占位快速完成（真实接入后可按阶段更新）.
      setProgressStage("完成")
      window.setTimeout(() => setProgressStage(null), 1200)
    }
  }

  function handlePatch(
    findingId: number,
    body: { status?: "accepted" | "ignored"; comment?: string },
  ) {
    patchFinding.mutate({ findingId, body })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 分析控制条 */}
      <div className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-4 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            onClick={handleAnalyze}
            disabled={startAnalysis.isPending || progressStage !== null}
          >
            {startAnalysis.isPending || progressStage !== null
              ? "分析中…"
              : "开始分析"}
          </Button>
          {/* 快速/深度 描边单选 (segmented) */}
          <div className="flex items-center gap-0 rounded-[var(--radius-DEFAULT)] border border-ink-500 bg-ink-100 p-0.5">
            <SegmentedButton
              active={mode === "quick"}
              onClick={() => setMode("quick")}
            >
              快速
            </SegmentedButton>
            <SegmentedButton
              active={mode === "deep"}
              onClick={() => setMode("deep")}
            >
              深度
            </SegmentedButton>
          </div>
        </div>
        <div className="flex flex-col gap-0.5 text-xs text-ink-700 md:items-end">
          <span>
            上次分析：{lastAnalysisAt ? formatTime(lastAnalysisAt) : "未分析"}
          </span>
          <span>模型参数：占位骨架（真实模型待接入）</span>
        </div>
      </div>

      {/* 分析进度条（占位快速完成） */}
      {progressStage !== null && (
        <div className="flex flex-col gap-1.5 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-3">
          <div className="flex items-center justify-between text-xs text-ink-700">
            <span>{progressStage}</span>
            <span className="font-mono">100%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-[var(--radius-full)] bg-ink-300">
            <div className="h-full w-full bg-ink-900 transition-all duration-500" />
          </div>
        </div>
      )}

      {/* 主区：左 findings 列表 + 右详情 */}
      <div className="flex min-h-[420px] gap-4">
        {/* 左：异常发现列表 */}
        <aside className="flex w-96 flex-shrink-0 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
          <div className="border-b border-ink-400 p-4">
            <h3 className="font-sans text-base font-semibold text-ink-900">
              异常发现
              <span className="ml-1.5 font-mono text-xs font-normal text-ink-700">
                ({findings.length})
              </span>
            </h3>
          </div>
          <div className="scroll-thin flex-1 overflow-y-auto p-2">
            {findingsQuery.isLoading && (
              <div className="px-3 py-10 text-center text-sm text-ink-700">
                加载中…
              </div>
            )}
            {!findingsQuery.isLoading && findings.length === 0 && (
              <div className="px-3 py-10 text-center text-sm text-ink-700">
                暂无异常发现。点击「开始分析」运行 AI 审查。
              </div>
            )}
            {findings.length > 0 && (
              <div className="space-y-1">
                {findings.map((f) => (
                  <FindingListItem
                    key={f.id}
                    finding={f}
                    active={f.id === selectedId}
                    onClick={() => setSelectedId(f.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* 右：异常详情 */}
        <section className="flex min-w-0 flex-1 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
          {selected ? (
            <FindingDetail
              finding={selected}
              onPatch={(body) => handlePatch(selected.id, body)}
              patching={patchFinding.isPending}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center p-10 text-sm text-ink-700">
              选择左侧异常发现查看详情。
            </div>
          )}
        </section>
      </div>

      {/* 底部多轮对话区 */}
      <ChatPanel taskId={taskId} chat={chatAnalyze} />

      {(startAnalysis.isError || patchFinding.isError || chatAnalyze.isError) && (
        <p className="text-sm text-ink-900">
          {(startAnalysis.error as Error)?.message ??
            (patchFinding.error as Error)?.message ??
            (chatAnalyze.error as Error)?.message ??
            "操作失败，请重试"}
        </p>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Severity 灰阶+形状双编码（单色原则，禁红黄绿）.
 * 高=黑底白字方块 / 中=深灰 / 低=浅灰.
 * ------------------------------------------------------------------------- */

const SEVERITY_LABEL: Record<Severity, string> = {
  high: "高",
  medium: "中",
  low: "低",
}

/** Severity 标 — 形状 + 灰阶双编码（docs §C4 单色硬底线）：
 *  高=黑底白字方块（rounded-none，最锐利） / 中=深灰圆角条 / 低=浅灰全圆胶囊.
 *  灰阶：高 bg-ink-900 text-ink-100 / 中 bg-ink-700 text-ink-100 / 低 bg-ink-300 text-ink-700. */
function SeverityBadge({ severity }: { severity: Severity }) {
  const styles: Record<Severity, string> = {
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

/* ---------------------------------------------------------------------------
 * 左侧异常发现列表项.
 * ------------------------------------------------------------------------- */

function FindingListItem({
  finding,
  active,
  onClick,
}: {
  finding: FindingItem
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full cursor-pointer p-3 text-left transition-colors",
        active
          ? "border-l-2 border-ink-900 bg-ink-300"
          : "border-l-2 border-transparent hover:bg-ink-300",
      )}
    >
      <div className="flex items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <span className="font-mono text-xs text-ink-700">#{finding.id}</span>
        <span className="ml-auto font-mono text-xs text-ink-700">
          {Math.round(finding.confidence * 100)}%
        </span>
      </div>
      <div className="mt-1.5 font-sans text-sm text-ink-900">
        {finding.type}
      </div>
      <p className="mt-0.5 line-clamp-2 text-xs text-ink-700">
        {finding.description}
      </p>
    </button>
  )
}

/* ---------------------------------------------------------------------------
 * 右侧异常详情.
 * ------------------------------------------------------------------------- */

function FindingDetail({
  finding,
  onPatch,
  patching,
}: {
  finding: FindingItem
  onPatch: (body: { status?: "accepted" | "ignored"; comment?: string }) => void
  patching: boolean
}) {
  const [commentDraft, setCommentDraft] = React.useState(finding.comment ?? "")

  React.useEffect(() => {
    setCommentDraft(finding.comment ?? "")
  }, [finding.id, finding.comment])

  // 时间分布小 bar（占位：8 根黑白灰 bar，按 severity 深浅映射）.
  const timeBars = React.useMemo(() => {
    const seed = finding.id
    return Array.from({ length: 8 }, (_, i) => {
      const v = ((seed * (i + 1)) % 5) / 4 // 0–1
      return v
    })
  }, [finding.id])

  return (
    <>
      <div className="border-b border-ink-400 p-4">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={finding.severity} />
          <span className="font-mono text-xs text-ink-700">
            #{finding.id}
          </span>
          <span
            className={cn(
              "ml-2 rounded-[var(--radius-DEFAULT)] px-1.5 py-0.5 text-[11px]",
              finding.status === "pending" && "bg-ink-300 text-ink-700",
              finding.status === "accepted" && "bg-ink-900 text-ink-100",
              finding.status === "ignored" && "bg-ink-500 text-ink-100",
            )}
          >
            {finding.status === "pending"
              ? "待处理"
              : finding.status === "accepted"
                ? "已采纳"
                : "已忽略"}
          </span>
        </div>
        <h3 className="mt-2 font-sans text-lg font-bold text-ink-900">
          {finding.type}
        </h3>
      </div>

      <div className="scroll-thin flex-1 space-y-5 overflow-y-auto p-4">
        {/* AI 推理摘要 */}
        <section>
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            AI 推理摘要
          </h4>
          <p className="text-sm text-ink-800">{finding.description}</p>
        </section>

        {/* 关联记录（占位） */}
        <section>
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            关联记录
          </h4>
          <div className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 p-3 text-xs text-ink-700">
            关联记录引用待接入（真实 agent 工具产出后展示 flow_record id）。
          </div>
        </section>

        {/* 时间分布黑白灰小 bar */}
        <section>
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            时间分布
          </h4>
          <div className="flex h-16 items-end gap-1.5">
            {timeBars.map((v, i) => (
              <div
                key={i}
                className="flex-1 bg-ink-800"
                style={{ height: `${Math.max(8, v * 100)}%` }}
              />
            ))}
          </div>
        </section>

        {/* 置信度灰阶水平条 */}
        <section>
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            置信度
          </h4>
          <div className="flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-[var(--radius-full)] bg-ink-200">
              <div
                className="h-full bg-ink-900"
                style={{ width: `${Math.round(finding.confidence * 100)}%` }}
              />
            </div>
            <span className="font-mono text-sm text-ink-900">
              {Math.round(finding.confidence * 100)}%
            </span>
          </div>
        </section>

        {/* 备注 */}
        <section>
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            备注
          </h4>
          <textarea
            value={commentDraft}
            onChange={(e) => setCommentDraft(e.target.value)}
            placeholder="添加备注…"
            rows={3}
            className="w-full resize-none rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 p-2 text-sm text-ink-900 outline-none focus:border-ink-800"
          />
        </section>
      </div>

      {/* 三按钮：采纳为告警 / 忽略 / 添加备注 */}
      <div className="flex items-center gap-2 border-t border-ink-400 p-3">
        <Button
          size="sm"
          onClick={() => onPatch({ status: "accepted" })}
          disabled={patching || finding.status === "accepted"}
        >
          采纳为告警
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPatch({ status: "ignored" })}
          disabled={patching || finding.status === "ignored"}
        >
          忽略
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPatch({ comment: commentDraft })}
          disabled={patching || commentDraft === (finding.comment ?? "")}
        >
          保存备注
        </Button>
      </div>
    </>
  )
}

/* ---------------------------------------------------------------------------
 * 底部多轮对话区.
 * AI 气泡 bg-ink-200 text-ink-900 / 用户气泡 bg-ink-900 text-ink-100.
 * ------------------------------------------------------------------------- */

interface ChatMessage {
  role: "user" | "ai"
  text: string
}

function ChatPanel({
  taskId,
  chat,
}: {
  taskId: number
  chat: ReturnType<typeof useChatAnalyze>
}) {
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const [input, setInput] = React.useState("")

  // taskId 变化时清空本地对话（切任务场景）.
  React.useEffect(() => {
    setMessages([])
    setInput("")
  }, [taskId])

  async function handleSend() {
    const text = input.trim()
    if (!text || chat.isPending) return
    setInput("")
    setMessages((prev) => [...prev, { role: "user", text }])
    try {
      const res = await chat.mutateAsync(text)
      setMessages((prev) => [...prev, { role: "ai", text: res.reply }])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "ai", text: "请求失败，请重试。" },
      ])
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-sans text-base font-semibold text-ink-900">
          对话追问
        </h3>
        <span className="text-xs text-ink-700">
          占位回复（真实推理待接入）
        </span>
      </div>

      <div className="scroll-thin flex max-h-64 flex-col gap-2.5 overflow-y-auto p-1">
        {messages.length === 0 && (
          <div className="py-6 text-center text-xs text-ink-700">
            向 AI 提问关于异常的细节（占位骨架，真实推理待接入）。
          </div>
        )}
        {messages.map((m, i) => (
          <ChatBubble key={i} message={m} />
        ))}
      </div>

      <div className="flex items-end gap-2 border-t border-ink-400 pt-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="提问…（Enter 发送，Shift+Enter 换行）"
          rows={1}
          className="max-h-32 flex-1 resize-none rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 p-2 text-sm text-ink-900 outline-none focus:border-ink-800"
        />
        <Button
          onClick={handleSend}
          disabled={chat.isPending || !input.trim()}
          size="icon"
          aria-label="发送"
        >
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"
  return (
    <div
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[80%] whitespace-pre-wrap rounded-[var(--radius-lg)] px-3 py-2 text-sm",
          isUser
            ? "bg-ink-900 text-ink-100"
            : "bg-ink-200 text-ink-900",
        )}
      >
        {message.text}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Segmented 单选按钮（快速/深度描边单选）.
 * ------------------------------------------------------------------------- */

function SegmentedButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-[var(--radius-DEFAULT)] px-3 py-1 text-xs transition-colors",
        active
          ? "bg-ink-900 font-bold text-ink-100"
          : "text-ink-700 hover:text-ink-900",
      )}
    >
      {children}
    </button>
  )
}

/** ISO → 本地时间字符串（YYYY-MM-DD HH:MM）. */
function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}
