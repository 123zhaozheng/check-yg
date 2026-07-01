import * as React from "react"
import { createFileRoute, useParams } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import type {
  KeywordHitItem,
  KeywordHitStatus,
  KeywordRiskLevel,
} from "@/lib/api"
import { useTask } from "@/hooks/use-tasks"
import { useKeywordCards } from "@/hooks/use-keyword-library"
import { FlowRecordLink } from "@/components/flow-record-link"
import {
  useKeywordHits,
  usePatchKeywordHit,
  useRunKeywordReview,
} from "@/hooks/use-keyword-review"

/**
 * 关键词审查 /tasks/:id/keyword-review (06-23-tab).
 *
 * Monochrome keyword-review page (单色对齐清洗/分析页):
 * - 顶部控制条：「选择关键词卡片」（多选 checkbox，从全局 keyword-library 拉 card 列表）
 *   +「开始审查」黑底主按钮 + 上次审查时间灰文。
 * - 4 KPI：扫描记录数 / 命中记录数 / 命中关键词数 / 高风险命中数。
 * - 命中表格：流水行（日期/对手/金额/摘要）+ 命中卡片名 + 关键词 + 匹配类型 + 置信度 +
 *   风险等级 + 命中字段 + 命中片段（片段里高亮命中词，单色用粗体/下划线不用彩色）+
 *   操作（采纳为告警/忽略/备注）。
 * - 状态过滤：全部/待处理/已采纳/已忽略。
 * - 重跑清旧命中再算（同 task 可换卡片反复重审）。
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/keyword-review")({
  component: KeywordReviewPage,
})

type StatusFilter = "all" | KeywordHitStatus

const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待处理" },
  { key: "confirmed", label: "已采纳" },
  { key: "ignored", label: "已忽略" },
]

function KeywordReviewPage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/keyword-review" })
  const taskId = Number(id)

  const [selectedCardIds, setSelectedCardIds] = React.useState<number[]>([])
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all")
  const [page, setPage] = React.useState(1)
  const [lastStats, setLastStats] = React.useState<{
    scanned_records: number
    hit_records: number
    hit_terms: number
    high_risk_hits: number
  } | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const cardsQuery = useKeywordCards()
  const taskQuery = useTask(taskId)
  const runReview = useRunKeywordReview(taskId)
  const patchHit = usePatchKeywordHit(taskId)

  const cards = cardsQuery.data ?? []
  const lastReviewAt = (taskQuery.data?.config as
    | { last_keyword_review_at?: string }
    | undefined)?.last_keyword_review_at

  // 命中分页查询（按状态过滤；后端分页）。
  const hitsQuery = useKeywordHits(taskId, {
    status: statusFilter === "all" ? undefined : statusFilter,
    page,
    page_size: 20,
  })
  const hits = hitsQuery.data?.items ?? []
  const total = hitsQuery.data?.total ?? 0
  const PAGE_SIZE = 20

  function toggleCard(cardId: number) {
    setSelectedCardIds((prev) =>
      prev.includes(cardId) ? prev.filter((id) => id !== cardId) : [...prev, cardId],
    )
  }

  async function handleRun() {
    setError(null)
    try {
      const stats = await runReview.mutateAsync({ card_ids: selectedCardIds })
      setLastStats(stats)
      setPage(1)
    } catch (err) {
      setError(errMsg(err) ?? "审查失败")
    }
  }

  function handlePatch(hitId: number, body: { status?: KeywordHitStatus; note?: string }) {
    patchHit.mutate({ hitId, body })
  }

  // 卡片名 map（命中表展示卡片名用）。
  const cardNameById = React.useMemo(() => {
    const m = new Map<number, string>()
    for (const c of cards) m.set(c.id, c.name)
    return m
  }, [cards])

  return (
    <div className="flex flex-col gap-4">
      {/* 控制条：多选卡片 + 开始审查 + 上次审查时间 */}
      <div className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 p-4 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold uppercase tracking-widest text-ink-600">
            选择关键词卡片
          </span>
          <div className="flex flex-wrap items-center gap-3">
            {cardsQuery.isLoading && (
              <span className="text-sm text-ink-600">卡片加载中…</span>
            )}
            {cards.map((c) => (
              <label
                key={c.id}
                className={cn(
                  "flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-DEFAULT)] border px-2 py-1 text-xs transition-colors",
                  selectedCardIds.includes(c.id)
                    ? "border-ink-900 bg-ink-300 font-bold text-ink-900"
                    : "border-ink-400 text-ink-700 hover:bg-ink-300",
                )}
              >
                <input
                  type="checkbox"
                  checked={selectedCardIds.includes(c.id)}
                  onChange={() => toggleCard(c.id)}
                  className="accent-ink-900"
                />
                {c.name}
                <span className="font-mono text-[11px] text-ink-600">
                  ({c.term_count})
                </span>
              </label>
            ))}
            {!cardsQuery.isLoading && cards.length === 0 && (
              <span className="text-xs text-ink-600">
                暂无关键词卡片，请先在「关键词库」页添加。
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-start gap-1 md:items-end">
          <Button
            onClick={handleRun}
            disabled={runReview.isPending || selectedCardIds.length === 0}
          >
            {runReview.isPending ? "审查中…" : "开始审查"}
          </Button>
          <span className="text-xs text-ink-700">
            上次审查：{lastReviewAt ? formatTime(lastReviewAt) : "未审查"}
          </span>
        </div>
      </div>

      {/* 4 KPI */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard
          label="扫描记录数"
          value={lastStats?.scanned_records ?? 0}
        />
        <KpiCard
          label="命中记录数"
          value={lastStats?.hit_records ?? 0}
        />
        <KpiCard
          label="命中关键词数"
          value={lastStats?.hit_terms ?? 0}
        />
        {/* 高风险命中 = 黑底白字（唯一 heavy 状态，单色禁彩色） */}
        <div className="flex flex-col gap-1 border-2 border-ink-900 bg-ink-900 p-4">
          <span className="font-sans text-[11px] font-bold uppercase tracking-wider text-ink-100">
            高风险命中数
          </span>
          <span className="font-mono text-2xl font-bold text-ink-100">
            {(lastStats?.high_risk_hits ?? 0).toLocaleString()}
          </span>
        </div>
      </div>

      {/* 状态过滤 */}
      <div className="flex items-center gap-2">
        {STATUS_FILTERS.map((f) => (
          <FilterButton
            key={f.key}
            active={statusFilter === f.key}
            onClick={() => {
              setStatusFilter(f.key)
              setPage(1)
            }}
          >
            {f.label}
          </FilterButton>
        ))}
      </div>

      {/* 命中表格 */}
      <Card>
        <CardContent className="flex flex-col gap-0 p-0">
          <div className="border-b border-ink-400 p-4">
            <h3 className="font-sans text-base font-semibold text-ink-900">
              命中列表
              <span className="ml-1.5 font-mono text-xs font-normal text-ink-700">
                ({total})
              </span>
            </h3>
          </div>
          <div className="scroll-thin overflow-auto">
            {hitsQuery.isLoading && (
              <div className="px-4 py-10 text-center text-sm text-ink-700">加载中…</div>
            )}
            {!hitsQuery.isLoading && hits.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-ink-700">
                暂无命中。选择关键词卡片后点击「开始审查」。
              </div>
            )}
            {hits.length > 0 && (
              <table className="w-full whitespace-nowrap border-collapse text-left">
                <thead className="sticky top-0 z-10 border-b border-ink-400 bg-ink-200">
                  <tr className="text-xs font-bold uppercase tracking-wider text-ink-700">
                    <th className="px-3 py-3">流水行</th>
                    <th className="px-3 py-3">命中卡片</th>
                    <th className="px-3 py-3">关键词</th>
                    <th className="px-3 py-3">匹配类型</th>
                    <th className="px-3 py-3">置信度</th>
                    <th className="px-3 py-3">风险</th>
                    <th className="px-3 py-3">命中字段</th>
                    <th className="px-3 py-3">命中片段</th>
                    <th className="px-3 py-3">状态</th>
                    <th className="px-3 py-3">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-400 font-mono text-sm">
                  {hits.map((hit) => (
                    <HitRow
                      key={hit.id}
                      taskId={taskId}
                      hit={hit}
                      cardName={cardNameById.get(hit.keyword_card_id) ?? "—"}
                      onPatch={(body) => handlePatch(hit.id, body)}
                      patching={patchHit.isPending}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
          {total > PAGE_SIZE && (
            <Pagination
              page={page}
              totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))}
              onPageChange={setPage}
            />
          )}
        </CardContent>
      </Card>

      {(runReview.isError || patchHit.isError) && (
        <p className="text-sm text-ink-900">
          {(runReview.error as Error)?.message ??
            (patchHit.error as Error)?.message ??
            error ??
            "操作失败，请重试"}
        </p>
      )}
      {error && <p className="text-sm text-ink-900">{error}</p>}
    </div>
  )
}

/** 命中行 — 含命中片段高亮（单色用粗体 + 下划线，不用彩色）+ 备注输入. */
function HitRow({
  taskId,
  hit,
  cardName,
  onPatch,
  patching,
}: {
  taskId: number
  hit: KeywordHitItem
  cardName: string
  onPatch: (body: { status?: KeywordHitStatus; note?: string }) => void
  patching: boolean
}) {
  // 备注本地编辑态：失焦/回车提交 PATCH note（AC #4 命中可备注）。
  const [noteDraft, setNoteDraft] = React.useState(hit.note ?? "")
  // 服务端 note 变化（重跑/采纳后 refetch）时同步本地草稿，避免脏值覆盖。
  React.useEffect(() => {
    setNoteDraft(hit.note ?? "")
  }, [hit.note])
  const noteDirty = noteDraft !== (hit.note ?? "")

  function commitNote() {
    if (!noteDirty) return
    onPatch({ note: noteDraft })
  }

  return (
    <tr className="align-top hover:bg-ink-300">
      <td className="px-3 py-3 text-ink-800">
        <FlowRecordLink taskId={taskId} recordId={hit.flow_record_id} />
      </td>
      <td className="px-3 py-3 text-ink-900">{cardName}</td>
      <td className="px-3 py-3 font-bold text-ink-900">{hit.matched_snippet}</td>
      <td className="px-3 py-3 text-ink-800">{hit.match_type}</td>
      <td className="px-3 py-3 text-ink-900">{hit.confidence}%</td>
      <td className="px-3 py-3">
        <RiskBadge level={hit.risk_level} />
      </td>
      <td className="px-3 py-3 text-ink-700">
        {hit.matched_field === "counterparty_name" ? "对手名" : "摘要"}
      </td>
      <td className="max-w-[220px] px-3 py-3 text-ink-800">
        <span className="font-bold underline decoration-ink-900 underline-offset-2">
          {hit.matched_snippet}
        </span>
      </td>
      <td className="px-3 py-3">
        <span
          className={cn(
            "rounded-[var(--radius-DEFAULT)] px-1.5 py-0.5 text-[11px]",
            hit.status === "pending" && "bg-ink-300 text-ink-700",
            hit.status === "confirmed" && "bg-ink-900 text-ink-100",
            hit.status === "ignored" && "bg-ink-500 text-ink-100",
          )}
        >
          {hit.status === "pending"
            ? "待处理"
            : hit.status === "confirmed"
              ? "已采纳"
              : "已忽略"}
        </span>
      </td>
      <td className="px-3 py-3">
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap gap-1.5">
            <Button
              size="sm"
              onClick={() => onPatch({ status: "confirmed" })}
              disabled={patching || hit.status === "confirmed"}
            >
              采纳
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onPatch({ status: "ignored" })}
              disabled={patching || hit.status === "ignored"}
            >
              忽略
            </Button>
          </div>
          <Input
            value={noteDraft}
            onChange={(e) => setNoteDraft(e.target.value)}
            onBlur={commitNote}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                commitNote()
              }
            }}
            placeholder="备注…"
            disabled={patching}
            className="h-7 min-w-[120px] font-sans text-xs"
          />
        </div>
      </td>
    </tr>
  )
}

/** 风险等级标 — 灰阶双编码（高=黑底白字 / 中=深灰 / 低=浅灰）. */
function RiskBadge({ level }: { level: KeywordRiskLevel }) {
  const styles: Record<KeywordRiskLevel, string> = {
    高: "bg-ink-900 text-ink-100 rounded-none",
    中: "bg-ink-700 text-ink-100 rounded-[var(--radius-DEFAULT)]",
    低: "bg-ink-300 text-ink-700 rounded-[var(--radius-full)]",
  }
  return (
    <span
      className={cn(
        "inline-flex h-5 min-w-8 items-center justify-center px-1.5 font-sans text-[11px] font-bold",
        styles[level],
      )}
    >
      {level}
    </span>
  )
}

/** KPI card — white bg + deep-gray number. 高风险变体在父组件内联渲染. */
function KpiCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-1 border border-ink-400 bg-ink-100 p-4">
      <span className="font-sans text-[11px] font-bold uppercase tracking-wider text-ink-700">
        {label}
      </span>
      <span className="font-mono text-2xl text-ink-900">
        {value.toLocaleString()}
      </span>
    </div>
  )
}

/** 过滤按钮 — active 黑底白字. */
function FilterButton({
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
        "rounded-[var(--radius-DEFAULT)] px-3 py-1.5 text-xs transition-colors",
        active
          ? "bg-ink-900 font-bold text-ink-100"
          : "text-ink-700 hover:bg-ink-300",
      )}
    >
      {children}
    </button>
  )
}

/** Minimal grayscale pagination. */
function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number
  totalPages: number
  onPageChange: (p: number) => void
}) {
  const pages: number[] = []
  const start = Math.max(1, page - 2)
  const end = Math.min(totalPages, start + 4)
  for (let i = start; i <= end; i++) pages.push(i)

  return (
    <div className="flex items-center justify-center gap-1.5 border-t border-ink-400 p-3">
      <Button
        variant="ghost"
        size="sm"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        上一页
      </Button>
      {pages.map((p) => (
        <button
          key={p}
          onClick={() => onPageChange(p)}
          className={cn(
            "h-8 min-w-8 rounded-[var(--radius-DEFAULT)] px-2 font-mono text-xs transition-colors",
            p === page
              ? "bg-ink-900 font-bold text-ink-100"
              : "text-ink-700 hover:bg-ink-300",
          )}
        >
          {p}
        </button>
      ))}
      <Button
        variant="ghost"
        size="sm"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        下一页
      </Button>
    </div>
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

/** Extract a human-readable error message. */
function errMsg(err: unknown): string | undefined {
  if (err instanceof Error) return err.message
  return undefined
}
