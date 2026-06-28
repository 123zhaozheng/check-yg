import * as React from "react"
import { createFileRoute, useParams } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { MessageSquare, Plus, Send, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Markdown } from "@/components/ui/markdown"
import { cn } from "@/lib/utils"
import type { FindingItem, Severity } from "@/lib/api"
import {
  useAnalysisProgress,
  useChatAnalyze,
  useConversationHistory,
  useConversations,
  useDeleteConversation,
  useFindingsLive,
  usePatchFinding,
  useStartAnalysis,
} from "@/hooks/use-analysis"
import { useTask } from "@/hooks/use-tasks"
import type { ChatSedimentedDimension, ChatToolTrace, LastAnalysisSummary } from "@/lib/api"

/**
 * AI 分析 /tasks/:id/analyze (06-26-ai-agent).
 *
 * 维度 = 结构化提示词；跑分析 = 每个 enabled 维度各跑一次 agentic agent.run。
 * 单色 AI 分析页（无 stitch 源稿，按 prd §十 + docs §C4，单色硬底线）:
 * - 控制条：「开始分析」黑底主按钮 + 上次分析时间灰文 + 维度数灰文（去快速/深度单选）.
 * - 跑分析异步化：POST /analyze 立即返 started → 订阅 WebSocket ``analysis.progress``
 *   事件（后端 cookie 鉴权通了，前端浏览器握手自动带 access_token cookie）：
 *   每跑完一个维度推一条 → 确定式进度条 (completed/total_dimensions) + 触发
 *   findings 轮询增量入左列。WS 断时降级轮询（useFindingsLive，兜底，不全开）.
 *   跑完（status=finished 或 completed>=total）停轮询 + 满格收尾.
 * - 左侧「维度详情」列表 (w-96): 按 severity 降序，severity 灰阶+形状双编码,
 *   选中项 border-l-2 + bg-ink-300. finding 实时增量（不等全跑完）.
 * - 右侧维度详情: detail_text 替代占位 description + 关联记录读 evidence_record_ids
 *   下钻 + 置信度灰阶水平条 + 三按钮（采纳为告警/忽略/保存备注 → PATCH）.
 *   （删 seeded 假时间分布 bar——MVP 直删假数据更干净.）
 * - 悬浮 AI 追问球（右下 fixed）：收起态圆球 → hover 扇形展开会话标题列表
 *   （首项固定 ＋新建会话，后续 = 会话首问题前 10 字）→ 点进会话展开面板（多轮 + 输入）.
 *   切任务自动收起 + 清 echo. 工具调用痕迹/沉淀可视化：每条 AI 气泡下方小字
 *   「🔍 已查询：…」（tool_traces，单色），sedimented_dimension 非空时气泡内嵌
 *   「已沉淀维度：XXX（草稿，待启用）」小卡（PRD §十）.
 *
 * agent 接入点结构遵循 docs/research/pydantic-ai-conventions.md (v1.107.0)
 * （后端 app/llm/analysis.py：AuditDeps + @agent.tool + ModelMessagesTypeAdapter
 * + message_history）.
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/analyze")({
  component: AnalyzePage,
})

function AnalyzePage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/analyze" })
  const taskId = Number(id)

  const [selectedId, setSelectedId] = React.useState<number | null>(null)
  // 跑分析中：true 时开 findings 轮询 + 进度条.
  const [running, setRunning] = React.useState(false)

  const taskQuery = useTask(taskId)
  const queryClient = useQueryClient()
  // WS analysis.progress 订阅（RVP 主通道）：跑分析中开。每跑完一个维度推一条：
  //   - 确定式进度条 (completed/total_dimensions)
  //   - invalidate findings → 左列实时增量（WS-primary，不等全跑完）
  // WS 断 → healthy=false → useFindingsLive 轮询接手（兜底，不全开防重复）.
  const { progress, healthy: wsHealthy } = useAnalysisProgress(taskId, running, () => {
    void queryClient.invalidateQueries({ queryKey: ["findings", "list", taskId] })
  })
  const findingsLive = useFindingsLive(taskId, running && !wsHealthy)
  const startAnalysis = useStartAnalysis(taskId)
  const patchFinding = usePatchFinding(taskId)

  const findings = findingsLive.data?.items ?? []
  const config = taskQuery.data?.config as
    | {
        last_analysis_at?: string
        last_analysis_summary?: LastAnalysisSummary
        active_conversation_id?: number | null
      }
    | undefined
  const lastAnalysisAt = config?.last_analysis_at
  const summary = config?.last_analysis_summary
  // 确定式进度：WS progress.completed（每维度增量）优先；WS 未通时回退
  // task.config.last_analysis_summary.completed（后端每维度也增量写库）.
  const wsCompleted = progress?.completed ?? 0
  const wsTotal = progress?.total ?? 0
  const totalDimensions = wsTotal || (summary?.total_dimensions ?? 0)
  const completed = wsCompleted || (summary?.completed ?? 0)
  // finished：WS 推到 completed>=total，或后端 summary.status=finished（双保险）.
  const finished =
    totalDimensions > 0 &&
    (completed >= totalDimensions || summary?.status === "finished")
  const findingsCount = findings.length

  // Auto-select the first finding when the list loads or changes.
  React.useEffect(() => {
    if (findings.length > 0 && !findings.some((f) => f.id === selectedId)) {
      setSelectedId(findings[0].id)
    }
    if (findings.length === 0 && !running) {
      setSelectedId(null)
    }
  }, [findings, selectedId, running])

  // 跑完收尾：后端在跑完时回填 last_analysis_summary.completed>=total → 停轮询.
  React.useEffect(() => {
    if (running && finished) {
      setRunning(false)
    }
  }, [running, finished])

  // WS 降级兜底：WS 断（!wsHealthy）时定时 refetch task，让 summary.completed
  // （后端每维度增量写库）跟上，进度条确定式仍可走。WS 通时 progress 直接驱动，不轮询.
  React.useEffect(() => {
    if (!running || wsHealthy) return
    const handle = setInterval(() => {
      void taskQuery.refetch()
    }, 1500)
    return () => clearInterval(handle)
  }, [running, wsHealthy, taskQuery])

  const selected = findings.find((f) => f.id === selectedId) ?? null

  async function handleAnalyze() {
    setRunning(true)
    try {
      await startAnalysis.mutateAsync()
    } catch {
      setRunning(false)
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
            disabled={startAnalysis.isPending || running}
          >
            {startAnalysis.isPending || running ? "分析中…" : "开始分析"}
          </Button>
        </div>
        <div className="flex flex-col gap-0.5 text-xs text-ink-700 md:items-end">
          <span>
            上次分析：{lastAnalysisAt ? formatTime(lastAnalysisAt) : "未分析"}
          </span>
          <span>
            启用维度：{totalDimensions > 0 ? `${totalDimensions} 个` : "—"}
            {running ? ` · 已发现 ${findingsCount} 条` : ""}
          </span>
        </div>
      </div>

      {/* 分析进度条（跑分析中显示；确定式：completed/total_dimensions 算百分比.
          WS progress.completed 每维度增量推送 → 进度条按维度数跳格. WS 未通时
          回退 task.config.last_analysis_summary.completed（每维度也写库）.
          totalDimensions 还没拿到（WS 首条未到 + summary 未回填）走不定 pulse.） */}
      {running && (
        <div className="flex flex-col gap-1.5 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-3">
          <div className="flex items-center justify-between text-xs text-ink-700">
            <span>
              {totalDimensions > 0
                ? `已完成 ${completed}/${totalDimensions} 个维度，已发现 ${findingsCount} 条`
                : "正在启动分析…"}
            </span>
            <span className="font-mono">
              {finished
                ? "100%"
                : totalDimensions > 0
                  ? `${Math.round((completed / totalDimensions) * 100)}%`
                  : "…"}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-[var(--radius-full)] bg-ink-300">
            {totalDimensions > 0 ? (
              <div
                className="h-full bg-ink-900 transition-all duration-500"
                style={{
                  width: `${Math.min(
                    100,
                    Math.round((completed / totalDimensions) * 100),
                  )}%`,
                }}
              />
            ) : (
              <div className="h-full w-1/3 animate-pulse rounded-[var(--radius-full)] bg-ink-700" />
            )}
          </div>
        </div>
      )}

      {/* 主区：左 findings 列表 + 右详情.
          固定高度（视口减去页眉/控制条/进度条预留），维度再多也不撑页 ——
          左右各自内部滚动（flex 滚动需子项 min-h-0）. */}
      <div className="flex h-[calc(100vh-13rem)] min-h-[460px] gap-4">
        {/* 左：维度详情列表 */}
        <aside className="flex min-h-0 w-96 flex-shrink-0 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
          <div className="border-b border-ink-400 p-4">
            <h3 className="font-sans text-base font-semibold text-ink-900">
              维度详情
              <span className="ml-1.5 font-mono text-xs font-normal text-ink-700">
                ({findings.length})
              </span>
            </h3>
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-2">
            {findingsLive.isLoading && findings.length === 0 && (
              <div className="px-3 py-10 text-center text-sm text-ink-700">
                加载中…
              </div>
            )}
            {!findingsLive.isLoading && findings.length === 0 && !running && (
              <div className="px-3 py-10 text-center text-sm text-ink-700">
                暂无维度发现。点击「开始分析」运行 AI 审查。
              </div>
            )}
            {findings.length === 0 && running && (
              <div className="px-3 py-10 text-center text-sm text-ink-700">
                正在跑维度分析，发现将实时显示…
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

        {/* 右：维度详情 */}
        <section className="flex min-h-0 min-w-0 flex-1 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
          {selected ? (
            <FindingDetail
              finding={selected}
              onPatch={(body) => handlePatch(selected.id, body)}
              patching={patchFinding.isPending}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center p-10 text-sm text-ink-700">
              选择左侧维度发现查看详情。
            </div>
          )}
        </section>
      </div>

      {(startAnalysis.isError || patchFinding.isError) && (
        <p className="text-sm text-ink-900">
          {(startAnalysis.error as Error)?.message ??
            (patchFinding.error as Error)?.message ??
            "操作失败，请重试"}
        </p>
      )}

      {/* 悬浮 AI 追问球（任务详情页内，非全局） */}
      <FloatingChatBall taskId={taskId} activeConversationId={config?.active_conversation_id ?? null} />
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
 *  高=黑底白字方块（rounded-none，最锐利） / 中=深灰圆角条 / 低=浅灰全圆胶囊. */
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
 * 左侧维度详情列表项.
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
        {finding.detail_text || finding.description}
      </p>
    </button>
  )
}

/* ---------------------------------------------------------------------------
 * 右侧维度详情.
 * detail_text 替代占位 description；关联记录读 evidence_record_ids 下钻.
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

  const evidenceIds = finding.evidence_record_ids ?? []

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
        {(finding.counterparty || finding.amount) && (
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-ink-700">
            {finding.counterparty && (
              <span>对手方：{finding.counterparty}</span>
            )}
            {finding.amount && <span>合计金额：{finding.amount}</span>}
          </div>
        )}
      </div>

      <div className="scroll-thin flex-1 space-y-5 overflow-y-auto p-4">
        {/* 维度分析正文（detail_text，Markdown 渲染） */}
        <section>
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            维度分析
          </h4>
          <Markdown>{finding.detail_text || finding.description}</Markdown>
        </section>

        {/* 关联记录（evidence_record_ids 下钻） */}
        <section>
          <h4 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-700">
            关联记录（命中流水行）
          </h4>
          {evidenceIds.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {evidenceIds.map((rid) => (
                <span
                  key={rid}
                  className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 px-2 py-0.5 font-mono text-xs text-ink-900"
                >
                  #{rid}
                </span>
              ))}
            </div>
          ) : (
            <div className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 p-3 text-xs text-ink-700">
              该维度未关联具体流水行。
            </div>
          )}
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

      {/* 三按钮：采纳为告警 / 忽略 / 保存备注 */}
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
 * 悬浮 AI 追问球（Q9 UX，user-feedback 改版）.
 * 收起态：右下 fixed 圆球。**点击**球 → 扇形展开会话标题列表（首项固定 ＋新建会话，
 *   后续 = 会话首问题前 10 字，列表可滚动，显示完整历史）。再点球 / 点空白收起.
 * 点历史会话 → 面板打开并**回放该会话历史消息**（GET .../conversations/{id}），可继续
 *   往下追问。点 ＋新建 → 面板打开空会话，首问后端懒建会话。切任务自动收起 + 清.
 * 展开态：固定右下面板（消息流 + 输入）。面板 header 不再重复 ＋（新建只在扇形里）.
 * 工具调用痕迹 / 沉淀可视化：每条 AI 气泡下方小字「🔍 已查询：…」+ 沉淀草稿小卡.
 * ------------------------------------------------------------------------- */

function FloatingChatBall({
  taskId,
  activeConversationId,
}: {
  taskId: number
  activeConversationId: number | null
}) {
  // view: ball（收起）/ panel（展开）。fanOpen = 扇形会话列表是否展开（仅 ball 态）.
  // panelConvId = 面板要展示的会话（null = 新会话）。
  const [view, setView] = React.useState<"ball" | "panel">("ball")
  const [fanOpen, setFanOpen] = React.useState(false)
  const [panelConvId, setPanelConvId] = React.useState<number | null>(null)

  const conversationsQuery = useConversations(taskId)
  const conversations = conversationsQuery.data?.items ?? []

  // 切任务：收起 + 关扇形 + 清面板会话.
  React.useEffect(() => {
    setView("ball")
    setFanOpen(false)
    setPanelConvId(null)
  }, [taskId])

  function openPanel(convId: number | null) {
    setPanelConvId(convId)
    setFanOpen(false)
    setView("panel")
  }

  return (
    <>
      {/* click-away 蒙层：扇形展开时点空白收起。独立 fixed 元素、z-40 低于内容层
          z-50 —— 否则蒙层（position:fixed）会盖在扇形/球（normal-flow）之上、吃掉点击，
          表现为扇形弹不开、点「新建会话」反而收起。 */}
      {view === "ball" && fanOpen && (
        <div
          className="pointer-events-auto fixed inset-0 z-40"
          onClick={() => setFanOpen(false)}
          aria-hidden
        />
      )}

      {/* 内容层（球 / 扇形 / 面板）：z-50 高于蒙层，蒙层不拦截这里面的点击 */}
      <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
        {/* 扇形会话标题列表（点击球展开；面板未展开时） */}
        {view === "ball" && fanOpen && (
          <ConversationFan
            conversations={conversations}
            // 高亮当前激活会话（后端 task.config.active_conversation_id）.
            activeConvId={panelConvId ?? activeConversationId}
            onPick={openPanel}
          />
        )}

        {/* 展开态面板（key 随会话变 → 切会话重挂载、重新回放该会话历史） */}
        {view === "panel" && (
          <ChatPanel
            key={panelConvId ?? "new"}
            taskId={taskId}
            conversationId={panelConvId}
            onClose={() => {
              setView("ball")
              setPanelConvId(null)
            }}
            // 首轮流新建会话后刷新会话列表，扇形里出现新会话（高亮用 activeConversationId）.
            onConversationCreated={() => {
              void conversationsQuery.refetch()
            }}
          />
        )}

        {/* 收起态圆球（点击切换扇形；面板打开时隐藏，由面板自身关闭） */}
        {view === "ball" && (
          <button
            onClick={() => setFanOpen((v) => !v)}
            aria-label="AI 追问"
            aria-expanded={fanOpen}
            className="pointer-events-auto flex size-12 items-center justify-center rounded-[var(--radius-full)] bg-ink-900 text-ink-100 shadow-[var(--shadow-popover)] transition-transform hover:scale-105"
          >
            <MessageSquare className="size-5" />
          </button>
        )}
      </div>
    </>
  )
}

/** 扇形展开会话标题列表 — 首项固定「＋ 新建会话」，后续 = 历史会话（可滚动，完整历史）. */
function ConversationFan({
  conversations,
  activeConvId,
  onPick,
}: {
  conversations: { id: number; title: string }[]
  activeConvId: number | null
  onPick: (convId: number | null) => void
}) {
  return (
    <div className="pointer-events-auto flex max-h-[60vh] flex-col items-end gap-1.5 overflow-y-auto pb-1 scroll-thin">
      {/* 新建会话（固定首项，视觉加号来自 icon） */}
      <FanItem label="新建会话" active={false} onClick={() => onPick(null)} icon />
      {/* 历史会话（按 id 升序，显示 #N · 前10字） */}
      {conversations.map((c, idx) => (
        <FanItem
          key={c.id}
          label={`#${idx + 1} · ${c.title || "未命名"}`}
          active={c.id === activeConvId}
          onClick={() => onPick(c.id)}
        />
      ))}
    </div>
  )
}

function FanItem({
  label,
  active,
  onClick,
  icon,
}: {
  label: string
  active: boolean
  onClick: () => void
  icon?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex max-w-[14rem] items-center gap-1.5 rounded-[var(--radius-DEFAULT)] border px-3 py-1.5 text-xs transition-colors",
        active
          ? "border-ink-900 bg-ink-300 font-semibold text-ink-900"
          : "border-ink-400 bg-ink-100 text-ink-800 hover:bg-ink-300",
      )}
    >
      {icon && <Plus className="size-3.5 shrink-0" />}
      <span className="truncate">{label}</span>
    </button>
  )
}

/** 一条追问面板消息（echo / 历史回放）。AI 消息可带 tool_traces + sedimented_dimension
 *  （后端 ChatResponse 新字段，PRD §十 工具痕迹/沉淀可视化；历史回放的 AI 消息不带痕迹）. */
interface ChatMessage {
  role: "user" | "ai"
  text: string
  toolTraces?: ChatToolTrace[]
  sedimentedDimension?: ChatSedimentedDimension | null
}

/**
 * 展开态追问面板 — 消息流 + 输入.
 *
 * 会话历史回放：``conversationId != null`` 时调 ``useConversationHistory`` 拉历史，
 * 首次到达 seed 进本地 messages（仅一次，``seededRef`` 挡住后续重取覆盖本地 echo）。
 * 新建会话（``conversationId == null``）：首轮流问后端懒建会话、返 conversation_id，
 * 记到 localConvId 供后续多轮；不回写父级 panelConvId（避免 key 变动重挂载丢消息）。
 */
function ChatPanel({
  taskId,
  conversationId,
  onClose,
  onConversationCreated,
}: {
  taskId: number
  conversationId: number | null
  onClose: () => void
  onConversationCreated: (convId: number) => void
}) {
  const chat = useChatAnalyze(taskId)
  const deleteConv = useDeleteConversation(taskId)
  // existing 会话才拉历史（null = 新会话，无历史）.
  const history = useConversationHistory(taskId, conversationId)
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const [input, setInput] = React.useState("")
  // localConvId：本面板当前会话（首轮新建前为 null，建会后置为新 id）.
  const [localConvId, setLocalConvId] = React.useState<number | null>(
    conversationId,
  )
  const seededRef = React.useRef(false)
  const scrollRef = React.useRef<HTMLDivElement>(null)

  // 历史回放：existing 会话首次拿到历史 → seed 进 messages（仅一次，不覆盖后续 echo）.
  React.useEffect(() => {
    if (conversationId != null && history.data && !seededRef.current) {
      setMessages(
        history.data.messages.map((m) => ({ role: m.role, text: m.text })),
      )
      seededRef.current = true
    }
  }, [conversationId, history.data])

  // 自动滚到底.
  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || chat.isPending) return
    setInput("")
    // 有本地 echo 后禁止历史 seed 覆盖（existing 会话历史慢到的极端情况）.
    seededRef.current = true
    setMessages((prev) => [...prev, { role: "user", text }])
    try {
      const res = await chat.mutateAsync({
        message: text,
        conversationId: localConvId,
      })
      // 首轮流建会话 → 后端返新 conversation_id，记到 localConvId（不回写父级）.
      if (localConvId == null) {
        setLocalConvId(res.conversation_id)
        onConversationCreated(res.conversation_id)
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          text: res.reply,
          toolTraces: res.tool_traces,
          sedimentedDimension: res.sedimented_dimension ?? null,
        },
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "ai", text: "请求失败，请重试。" },
      ])
    }
  }

  async function handleDeleteConversation() {
    if (localConvId == null) return
    try {
      await deleteConv.mutateAsync(localConvId)
      // 删完收起回扇形（该会话已不在列表）.
      onClose()
    } catch {
      // 删失败时停留.
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const historyLoading =
    conversationId != null && history.isLoading && messages.length === 0

  return (
    <div className="pointer-events-auto flex h-[28rem] w-96 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 shadow-[var(--shadow-popover)]">
      {/* header：标题 + 删除/收起（去掉了重复的 ＋ 新建——新建只在扇形里） */}
      <div className="flex items-center justify-between border-b border-ink-400 px-4 py-2.5">
        <div className="min-w-0">
          <h3 className="font-sans text-sm font-semibold text-ink-900">AI 追问</h3>
          <p className="truncate font-mono text-[11px] text-ink-700">
            {localConvId != null ? `会话 #${localConvId}` : "新会话"}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="删除会话"
            title="删除会话"
            onClick={handleDeleteConversation}
            disabled={deleteConv.isPending || localConvId == null}
          >
            <Trash2 className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="收起"
            title="收起"
            onClick={onClose}
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      {/* 消息流（AI 文本走 Markdown 渲染） */}
      <div
        ref={scrollRef}
        className="scroll-thin flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3"
      >
        {messages.length === 0 && (
          <div className="py-6 text-center text-xs text-ink-700">
            {historyLoading
              ? "加载历史会话…"
              : "向 AI 提问关于维度发现的细节，或让它沉淀新审查维度。"}
          </div>
        )}
        {messages.map((m, i) => (
          <ChatBubble
            key={i}
            role={m.role}
            text={m.text}
            toolTraces={m.toolTraces}
            sedimentedDimension={m.sedimentedDimension}
          />
        ))}
      </div>

      {/* 输入框 + 发送 */}
      <div className="flex items-end gap-2 border-t border-ink-400 p-3">
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

function ChatBubble({
  role,
  text,
  toolTraces,
  sedimentedDimension,
}: {
  role: "user" | "ai"
  text: string
  toolTraces?: ChatToolTrace[]
  sedimentedDimension?: ChatSedimentedDimension | null
}) {
  const isUser = role === "user"
  const traces = toolTraces ?? []
  const hasTraces = traces.length > 0
  const hasSediment = sedimentedDimension != null
  // AI 文本走 Markdown（标题/列表/加粗/代码/表格）；用户文本纯文本换行.
  // AI 气泡有工具痕迹/沉淀卡时，下方再叠一小块放这些副信息（单色，紧贴气泡）.
  return (
    <div className={cn("flex flex-col gap-1", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[90%] rounded-[var(--radius-lg)] px-3 py-2 text-sm",
          isUser ? "bg-ink-900 text-ink-100" : "bg-ink-200 text-ink-900",
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap break-words">{text}</span>
        ) : (
          <Markdown>{text}</Markdown>
        )}
      </div>
      {/* 工具调用痕迹：每条 trace 一行小字「🔍 已查询：{summary}」（PRD §十，单色） */}
      {hasTraces && (
        <div className="flex max-w-[90%] flex-col gap-0.5 pl-1">
          {traces.map((t, i) => (
            <span key={i} className="text-[11px] leading-tight text-ink-700">
              🔍 已查询：{t.summary}
            </span>
          ))}
        </div>
      )}
      {/* 沉淀可视化：本轮流问沉淀出草稿维度 → 小卡「已沉淀维度：XXX（草稿，待启用）」 */}
      {hasSediment && sedimentedDimension && (
        <div className="max-w-[90%] rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 px-2.5 py-1.5 text-[11px] text-ink-900">
          已沉淀维度：{sedimentedDimension.name}（
          {SEVERITY_LABEL[severityKey(sedimentedDimension.severity)]}，草稿，待启用）
          <span className="ml-1 text-ink-700">— 去维度管理页启用</span>
        </div>
      )}
    </div>
  )
}

/** 把后端 severity (high|medium|low) 映射成 SEVERITY_LABEL 的 key（同值，类型守卫）. */
function severityKey(s: string): Severity {
  return s === "high" || s === "medium" || s === "low" ? s : "medium"
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
