import * as React from "react"
import { createFileRoute, useParams } from "@tanstack/react-router"
import {
  ChevronRight,
  ChevronDown,
  Download,
  RotateCcw,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { FlowRecordItem, FindingItem, RecordType } from "@/lib/api"
import {
  useCommitCleaning,
  useExcludedRecords,
  useExportCleaningLog,
  useRestoreRecord,
  useTaskRecords,
} from "@/hooks/use-records"
import { useFindings, usePatchFinding } from "@/hooks/use-analysis"

/**
 * 清洗标准化 /tasks/:id/clean (docs §C3).
 *
 * Monochrome cleaning page (stitch_/cleaning_standardization/code.html, 单色改造):
 * - Header: 面包屑 + "清洗与标准化" + 副标题 + 导出日志 (描边) + 提交清洗数据 (黑底主).
 * - 4 KPI cards: 原始记录数 / 标准化记录数 / 排除记录数 / 异常数. The 异常数
 *   card is the ONLY "heavy" state — black bg + white bold (bg-ink-900 text-ink-100
 *   font-bold), never red (#ba1a1a banned).
 * - Left rule panel (w-80): static rule list (决策4), selected item has a left
 *   black bar (border-l-2 border-ink-900). No hit counts (not fabricated).
 * - Right standardized table: 记录ID/日期/收支/金额(等宽)/对方/渠道/摘要. Click a
 *   row to expand 原始↔标准对照 (双栏, bg-ink-200 高亮, 禁彩色 diff).
 * - 排除项视图: tab toggle between excluded / unparsed, each row has a 捞回
 *   button (POST restore + invalidate).
 * - TanStack Query paginates records/excluded.
 *
 * 清洗不删减: standard + unparsed + excluded all come from the same
 * flow_records table; restore marks a row restored (row stays, never deleted).
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/clean")({
  component: CleanPage,
})

/** Static cleaning rules (决策4) — display only, not clickable/configurable. */
const CLEANING_RULES: { title: string; desc: string }[] = [
  {
    title: "日期标准化",
    desc: "统一为 YYYY-MM-DD hh:mm:ss，缺年结合画像推断",
  },
  {
    title: "收支方向推断",
    desc: "raw_amount 正负号 + amount_sign_rule（信用卡交由 LLM）",
  },
  {
    title: "金额去符号",
    desc: "amount 始终正数；raw_amount 保留原始正负号",
  },
  {
    title: "对手账号纯数字化",
    desc: "仅保留纯数字账号/卡号，剔除开户行等非数字内容",
  },
  {
    title: "噪音行过滤",
    desc: "合计/小计/余额/页脚/页眉/空行 → unparsed（不删）",
  },
  {
    title: "非流水表识别",
    desc: "classifier 判定非流水的整表 → excluded（不删）",
  },
]

type ViewTab = "standard" | "excluded"

function CleanPage() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id/clean" })
  const taskId = Number(id)

  const [activeTab, setActiveTab] = React.useState<ViewTab>("standard")
  const [excludedSubTab, setExcludedSubTab] = React.useState<"excluded" | "unparsed">("excluded")
  const [activeRule, setActiveRule] = React.useState(0)
  const [standardPage, setStandardPage] = React.useState(1)
  const [excludedPage, setExcludedPage] = React.useState(1)
  // 应用规则 aside 折叠态（06-23-tab）：默认收起（true），展开恢复规则列表。
  const [rulesCollapsed, setRulesCollapsed] = React.useState(true)

  const PAGE_SIZE = 20

  // Standard records (paginated) — the cleaned, downstream-usable rows.
  const standardQuery = useTaskRecords(taskId, {
    record_type: "standard",
    page: standardPage,
    page_size: PAGE_SIZE,
  })

  // Excluded view records (paginated) — one type at a time so the 非流水表 /
  // 噪音行 sub-tabs paginate independently (server-side filter by record_type).
  // Active only (restored rows drop out). Reset to page 1 when the sub-tab
  // changes so the user doesn't land on an out-of-range page for the new type.
  const excludedQuery = useExcludedRecords(taskId, {
    record_type: excludedSubTab,
    page: excludedPage,
    page_size: PAGE_SIZE,
  })

  // KPI counts: 3 parallel count queries (page_size=1 reads total only).
  // 异常数 = unparsed + excluded + standard with is_valid=false. Per PRD,
  // pick a consistent口径: unparsed + excluded (the 不删减保留的排除项).
  const stdCountQuery = useTaskRecords(taskId, {
    record_type: "standard",
    page: 1,
    page_size: 1,
  })
  const unparsedCountQuery = useTaskRecords(taskId, {
    record_type: "unparsed",
    page: 1,
    page_size: 1,
  })
  const excludedCountQuery = useTaskRecords(taskId, {
    record_type: "excluded",
    page: 1,
    page_size: 1,
  })

  const stdCount = stdCountQuery.data?.total ?? 0
  const unparsedCount = unparsedCountQuery.data?.total ?? 0
  const excludedCount = excludedCountQuery.data?.total ?? 0
  const originalCount = stdCount + unparsedCount + excludedCount
  const anomalyCount = unparsedCount + excludedCount

  const commit = useCommitCleaning(taskId)
  const exportLog = useExportCleaningLog(taskId)
  const restore = useRestoreRecord(taskId)

  // 余额校验：复用 findings 体系，按 source=balance_check 单取（后端不传 source 时排除）.
  const balanceFindings = useFindings(taskId, { source: "balance_check" })
  const patchFinding = usePatchFinding(taskId)

  const [committed, setCommitted] = React.useState(false)
  React.useEffect(() => {
    if (commit.isSuccess) setCommitted(true)
  }, [commit.isSuccess])

  // Reset the excluded-view page to 1 when the sub-tab changes — the new type
  // has its own row count, so the current page index may be out of range.
  React.useEffect(() => {
    setExcludedPage(1)
  }, [excludedSubTab])

  function handleExport(format: "csv" | "json") {
    exportLog.mutate(format)
  }

  function handleRestore(recordId: number) {
    restore.mutate(recordId)
  }

  function handlePatchFinding(
    findingId: number,
    body: { status?: "accepted" | "ignored"; comment?: string },
  ) {
    patchFinding.mutate({ findingId, body })
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Control bar: 导出日志 + 提交清洗数据 (title/h1 dropped — layout shell
       * PageHeader already shows the task name + sub-page is signaled by the
       * tab nav highlight). */}
      <div className="flex items-center justify-end gap-2">
        <Button variant="secondary" onClick={() => handleExport("csv")}>
          <Download className="size-4" />
          导出日志
        </Button>
        <Button
          onClick={() => commit.mutate()}
          disabled={commit.isPending || committed}
        >
          {committed ? "已提交" : "提交清洗数据"}
        </Button>
      </div>

      {/* 4 KPI cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="原始记录数" value={originalCount} />
        <KpiCard label="标准化记录数" value={stdCount} />
        <KpiCard label="排除记录数" value={excludedCount + unparsedCount} />
        {/* 异常数 = black bg + white bold — the ONLY heavy state. Never red. */}
        <div className="flex flex-col gap-1 border-2 border-ink-900 bg-ink-900 p-4">
          <span className="font-sans text-[11px] font-bold uppercase tracking-wider text-ink-100">
            异常数
          </span>
          <span className="font-mono text-2xl font-bold text-ink-100">
            {anomalyCount.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Tab toggle: 标准化结果 / 排除项 */}
      <div className="flex items-center gap-6 border-b border-ink-400">
        <TabButton
          active={activeTab === "standard"}
          onClick={() => setActiveTab("standard")}
        >
          标准化结果
        </TabButton>
        <TabButton
          active={activeTab === "excluded"}
          onClick={() => setActiveTab("excluded")}
        >
          排除项
          {anomalyCount > 0 && (
            <span className="ml-1.5 rounded-[var(--radius-DEFAULT)] bg-ink-300 px-1.5 py-0.5 font-mono text-[11px] text-ink-700">
              {anomalyCount}
            </span>
          )}
        </TabButton>
      </div>

      {/* Main split: rule panel (left) + content (right) */}
      <div className="flex min-h-[420px] gap-4">
        {/* Left: static rule panel — 可折叠（06-23-tab），默认收起 */}
        {rulesCollapsed ? (
          <button
            onClick={() => setRulesCollapsed(false)}
            className="flex w-10 flex-shrink-0 flex-col items-center gap-2 rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 py-3 text-ink-700 transition-colors hover:bg-ink-300"
            aria-label="展开应用规则"
            title="展开应用规则"
          >
            <ChevronRight className="size-4" />
            <span className="font-sans text-xs font-semibold [writing-mode:vertical-rl]">
              应用规则
            </span>
          </button>
        ) : (
          <aside className="flex w-80 flex-shrink-0 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
            <div className="flex items-center justify-between border-b border-ink-400 p-4">
              <h3 className="font-sans text-base font-semibold text-ink-900">
                应用规则
              </h3>
              <button
                onClick={() => setRulesCollapsed(true)}
                aria-label="收起应用规则"
                title="收起应用规则"
                className="text-ink-600 transition-colors hover:text-ink-900"
              >
                <ChevronDown className="size-4" />
              </button>
            </div>
            <div className="scroll-thin flex-1 space-y-1 overflow-y-auto p-2">
              {CLEANING_RULES.map((rule, idx) => {
                const isActive = idx === activeRule
                return (
                  <button
                    key={rule.title}
                    onClick={() => setActiveRule(idx)}
                    className={cn(
                      "mb-1 w-full cursor-pointer p-3 text-left transition-colors",
                      isActive
                        ? "border-l-2 border-ink-900 bg-ink-300"
                        : "border-l-2 border-transparent hover:bg-ink-300",
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span
                        className={cn(
                          "font-sans text-sm",
                          isActive ? "font-medium text-ink-900" : "text-ink-800",
                        )}
                      >
                        {rule.title}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-ink-700">{rule.desc}</p>
                  </button>
                )
              })}
            </div>
          </aside>
        )}

        {/* Right: standard table or excluded view */}
        <section className="flex min-w-0 flex-1 flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
          {activeTab === "standard" ? (
            <StandardRecordsTable
              items={standardQuery.data?.items ?? []}
              total={standardQuery.data?.total ?? 0}
              page={standardPage}
              pageSize={PAGE_SIZE}
              onPageChange={setStandardPage}
              isLoading={standardQuery.isLoading}
            />
          ) : (
            <ExcludedView
              items={excludedQuery.data?.items ?? []}
              total={excludedQuery.data?.total ?? 0}
              page={excludedPage}
              pageSize={PAGE_SIZE}
              onPageChange={setExcludedPage}
              subTab={excludedSubTab}
              onSubTabChange={setExcludedSubTab}
              onRestore={handleRestore}
              restoringId={restore.isPending ? restore.variables ?? null : null}
              isLoading={excludedQuery.isLoading}
            />
          )}
        </section>
      </div>

      {/* 余额校验区：上一行余额 ± 本笔收支 = 本行余额，对不上就指出.
          无余额列文档 → 后端不产 finding，列表空（任务级不细分"无余额列"与"全部平衡"）. */}
      <BalanceCheckSection
        findings={balanceFindings.data?.items ?? []}
        isLoading={balanceFindings.isLoading}
        onPatch={handlePatchFinding}
        patching={patchFinding.isPending}
        patchingId={patchFinding.isPending ? patchFinding.variables?.findingId ?? null : null}
      />

      {(commit.isError || exportLog.isError || restore.isError) && (
        <p className="text-sm text-ink-900">
          {(commit.error as Error)?.message ??
            (exportLog.error as Error)?.message ??
            (restore.error as Error)?.message ??
            "操作失败，请重试"}
        </p>
      )}
    </div>
  )
}

/** KPI card — white bg + deep-gray number. The anomaly card is rendered inline
 *  (black bg variant) in the parent, never here. */
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

/** Tab button — active gets bold + bottom black bar. */
function TabButton({
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
        "relative whitespace-nowrap pb-3 pt-1 text-sm transition-colors",
        active ? "font-bold text-ink-900" : "text-ink-700 hover:text-ink-900",
      )}
    >
      {children}
      {active && (
        <span className="absolute inset-x-0 -bottom-px h-0.5 bg-ink-900" />
      )}
    </button>
  )
}

/**
 * 余额校验区 — source=balance_check 的 finding 列表（PRD §六）.
 *
 * 单色卡片面板（border-ink-400 bg-ink-100，跟 clean 页其它卡片同风格）.
 * 每条不符行：状态 pill（灰阶编码，参考 analyze.tsx）+ 行号/对手方/金额
 * + detail_text（等宽数字）+ 采纳/忽略按钮（按 status + patching + patchingId
 * 做 disabled，参考 analyze.tsx FindingDetail 三按钮逻辑）.
 * 无余额列文档 → 后端不产 finding，列表空（任务级不细分）.
 */
function BalanceCheckSection({
  findings,
  isLoading,
  onPatch,
  patching,
  patchingId,
}: {
  findings: FindingItem[]
  isLoading: boolean
  onPatch: (
    findingId: number,
    body: { status?: "accepted" | "ignored"; comment?: string },
  ) => void
  patching: boolean
  patchingId: number | null
}) {
  return (
    <section className="flex flex-col rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100">
      <div className="border-b border-ink-400 p-4">
        <h3 className="font-sans text-base font-semibold text-ink-900">
          余额校验
          <span className="ml-1.5 font-mono text-xs font-normal text-ink-700">
            ({findings.length})
          </span>
        </h3>
      </div>
      <div className="flex-1">
        {isLoading && (
          <div className="px-4 py-10 text-center text-sm text-ink-700">
            加载中…
          </div>
        )}
        {!isLoading && findings.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-ink-700">
            暂无余额校验异常
          </div>
        )}
        {findings.length > 0 && (
          <div className="divide-y divide-ink-400">
            {findings.map((finding) => (
              <BalanceCheckRow
                key={finding.id}
                finding={finding}
                onPatch={onPatch}
                patching={patching}
                isPatchingThis={
                  patching && patchingId === finding.id
                }
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

/** 单条余额校验不符行：状态 pill + 元信息 + detail_text + 采纳/忽略按钮. */
function BalanceCheckRow({
  finding,
  onPatch,
  patching,
  isPatchingThis,
}: {
  finding: FindingItem
  onPatch: (
    findingId: number,
    body: { status?: "accepted" | "ignored"; comment?: string },
  ) => void
  patching: boolean
  isPatchingThis: boolean
}) {
  // aggregate finding（文档级）：evidence_record_ids 空 → 显示「文档级」而非行号.
  const isAggregate =
    !finding.evidence_record_ids || finding.evidence_record_ids.length === 0

  return (
    <div className="flex flex-col gap-2 p-4">
      {/* 元信息行：状态 pill + 文档级标识 + 金额 */}
      <div className="flex flex-wrap items-center gap-2">
        <BalanceStatusPill status={finding.status} />
        <span className="font-mono text-xs text-ink-700">
          #{isAggregate ? finding.id : finding.evidence_record_ids?.[0]}
        </span>
        {isAggregate && (
          <span className="text-xs text-ink-700">文档级</span>
        )}
        {finding.counterparty && (
          <span className="text-xs text-ink-700">
            对手方：{finding.counterparty}
          </span>
        )}
        {finding.amount && (
          <span className="font-mono text-xs text-ink-900">
            金额：{finding.amount}
          </span>
        )}
      </div>
      {/* detail_text：期望/实际/差额算式，等宽数字 */}
      {finding.detail_text && (
        <p className="whitespace-pre-wrap font-mono text-xs text-ink-800">
          {finding.detail_text}
        </p>
      )}
      {/* 备注（已有时显示） */}
      {finding.comment && (
        <p className="rounded-[var(--radius-DEFAULT)] bg-ink-200 px-2 py-1 text-xs text-ink-700">
          备注：{finding.comment}
        </p>
      )}
      {/* 操作按钮：采纳为告警 / 忽略 */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={() => onPatch(finding.id, { status: "accepted" })}
          disabled={patching || finding.status === "accepted"}
        >
          采纳为告警
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPatch(finding.id, { status: "ignored" })}
          disabled={patching || finding.status === "ignored"}
        >
          忽略
        </Button>
        {isPatchingThis && (
          <span className="text-[11px] text-ink-700">提交中…</span>
        )}
      </div>
    </div>
  )
}

/**
 * 余额校验状态 pill — 灰阶编码（单色原则，参考 analyze.tsx 状态 pill 写法）.
 * accepted=黑底 / ignored=深灰 / pending=浅灰.
 */
function BalanceStatusPill({
  status,
}: {
  status: FindingItem["status"]
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[var(--radius-DEFAULT)] px-1.5 py-0.5 text-[11px] font-bold",
        status === "accepted" && "bg-ink-900 text-ink-100",
        status === "ignored" && "bg-ink-500 text-ink-100",
        status === "pending" && "bg-ink-300 text-ink-700",
      )}
    >
      {status === "pending"
        ? "待处理"
        : status === "accepted"
          ? "已采纳"
          : "已忽略"}
    </span>
  )
}

/** Standardized records table with row expand (原始↔标准对照). */
function StandardRecordsTable({
  items,
  total,
  page,
  pageSize,
  onPageChange,
  isLoading,
}: {
  items: FlowRecordItem[]
  total: number
  page: number
  pageSize: number
  onPageChange: (p: number) => void
  isLoading: boolean
}) {
  const [expandedId, setExpandedId] = React.useState<number | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <>
      <div className="border-b border-ink-400 p-4">
        <h3 className="font-sans text-base font-semibold text-ink-900">
          标准化结果
        </h3>
      </div>
      <div className="scroll-thin flex-1 overflow-auto">
        {isLoading && (
          <div className="px-4 py-10 text-center text-sm text-ink-700">
            加载中…
          </div>
        )}
        {!isLoading && items.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-ink-700">
            暂无标准化记录。
          </div>
        )}
        {items.length > 0 && (
          <table className="w-full whitespace-nowrap border-collapse text-left">
            <thead className="sticky top-0 z-10 border-b border-ink-400 bg-ink-200">
              <tr className="text-xs font-bold uppercase tracking-wider text-ink-700">
                <th className="w-8 px-3 py-3" />
                <th className="px-3 py-3">记录ID</th>
                <th className="px-3 py-3">日期</th>
                <th className="px-3 py-3">收支</th>
                <th className="px-3 py-3 text-right">金额</th>
                <th className="px-3 py-3 text-right">余额</th>
                <th className="px-3 py-3">对方</th>
                <th className="px-3 py-3">渠道</th>
                <th className="px-3 py-3">摘要</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-400 font-mono text-sm">
              {items.map((row) => {
                const expanded = expandedId === row.id
                return (
                  <React.Fragment key={row.id}>
                    <tr
                      role="button"
                      tabIndex={0}
                      onClick={() => setExpandedId(expanded ? null : row.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault()
                          setExpandedId(expanded ? null : row.id)
                        }
                      }}
                      className={cn(
                        "cursor-pointer transition-colors hover:bg-ink-300",
                        expanded && "bg-ink-300",
                      )}
                    >
                      <td className="px-3 py-3 text-ink-700">
                        {expanded ? (
                          <ChevronDown className="size-4" />
                        ) : (
                          <ChevronRight className="size-4" />
                        )}
                      </td>
                      <td className="px-3 py-3 text-ink-900">#{row.id}</td>
                      <td className="px-3 py-3 text-ink-800">
                        {row.transaction_time || "—"}
                      </td>
                      <td className="px-3 py-3 text-ink-800">
                        {row.transaction_type || "—"}
                      </td>
                      <td className="px-3 py-3 text-right text-ink-900">
                        {row.amount || "—"}
                      </td>
                      <td className="px-3 py-3 text-right text-ink-800">
                        {row.balance || "—"}
                      </td>
                      <td className="px-3 py-3 text-ink-800">
                        {row.counterparty_name || "—"}
                      </td>
                      <td className="px-3 py-3 text-ink-700">
                        {row.channel || "—"}
                      </td>
                      <td className="max-w-[280px] truncate px-3 py-3 text-ink-700">
                        {row.summary || "—"}
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="border-b-2 border-ink-400 bg-ink-300">
                        <td colSpan={9} className="p-0">
                          <RawVsStandardCompare row={row} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
      {total > pageSize && (
        <Pagination
          page={page}
          totalPages={totalPages}
          onPageChange={onPageChange}
        />
      )}
    </>
  )
}

/** 原始↔标准对照 (双栏). 原始 cells from raw_payload; 标准 from the row.
 *  Differences highlighted with bg-ink-200 (light gray), never a colored diff. */
function RawVsStandardCompare({ row }: { row: FlowRecordItem }) {
  const rawCells = row.raw_payload?.cells ?? []
  const standardFields: { label: string; value: string }[] = [
    { label: "交易时间", value: row.transaction_time ?? "" },
    { label: "交易对手", value: row.counterparty_name ?? "" },
    { label: "对手账号", value: row.counterparty_account ?? "" },
    { label: "金额", value: row.amount ?? "" },
    { label: "余额", value: row.balance ?? "" },
    { label: "原始金额", value: row.raw_amount ?? "" },
    { label: "摘要", value: row.summary ?? "" },
    { label: "收支类型", value: row.transaction_type ?? "" },
  ]

  return (
    <div className="flex gap-6 px-6 py-4 font-sans text-sm">
      {/* Original raw */}
      <div className="flex-1">
        <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-700">
          原始数据（来源：{row.channel || "未知渠道"}）
        </div>
        <div className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-1.5 font-mono text-xs">
          {rawCells.map((cell, idx) => (
            <React.Fragment key={idx}>
              <div className="text-ink-700">单元格 {idx + 1}:</div>
              <div className="bg-ink-200 px-1.5 py-0.5 text-ink-900">
                {cell || "（空）"}
              </div>
            </React.Fragment>
          ))}
          {rawCells.length === 0 && (
            <div className="col-span-2 text-ink-700">无原始数据</div>
          )}
        </div>
      </div>
      {/* Standard */}
      <div className="flex-1 border-l border-ink-400 pl-6">
        <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-900">
          标准化（已应用 schema）
        </div>
        <div className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-1.5 font-mono text-xs">
          {standardFields.map((f) => (
            <React.Fragment key={f.label}>
              <div className="text-ink-700">{f.label}:</div>
              <div className="border border-ink-400 bg-ink-100 px-1.5 py-0.5 font-bold text-ink-900">
                {f.value || "（空）"}
              </div>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  )
}

/** 排除项视图 — excluded / unparsed sub-tab, each row has a 捞回 button. */
function ExcludedView({
  items,
  total,
  page,
  pageSize,
  onPageChange,
  subTab,
  onSubTabChange,
  onRestore,
  restoringId,
  isLoading,
}: {
  items: FlowRecordItem[]
  total: number
  page: number
  pageSize: number
  onPageChange: (p: number) => void
  subTab: "excluded" | "unparsed"
  onSubTabChange: (t: "excluded" | "unparsed") => void
  onRestore: (id: number) => void
  restoringId: number | null
  isLoading: boolean
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <>
      <div className="flex items-center justify-between border-b border-ink-400 p-4">
        <h3 className="font-sans text-base font-semibold text-ink-900">
          排除项（可捞回）
        </h3>
        <div className="flex items-center gap-2">
          <SubTabButton
            active={subTab === "excluded"}
            onClick={() => onSubTabChange("excluded")}
          >
            非流水表
          </SubTabButton>
          <SubTabButton
            active={subTab === "unparsed"}
            onClick={() => onSubTabChange("unparsed")}
          >
            噪音行
          </SubTabButton>
        </div>
      </div>
      <div className="scroll-thin flex-1 overflow-auto">
        {isLoading && (
          <div className="px-4 py-10 text-center text-sm text-ink-700">
            加载中…
          </div>
        )}
        {!isLoading && items.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-ink-700">
            暂无{subTab === "excluded" ? "非流水表" : "噪音行"}记录。
          </div>
        )}
        {items.length > 0 && (
          <div className="divide-y divide-ink-400">
            {items.map((row) => (
              <ExcludedRow
                key={row.id}
                row={row}
                onRestore={() => onRestore(row.id)}
                isRestoring={restoringId === row.id}
              />
            ))}
          </div>
        )}
      </div>
      {total > pageSize && (
        <Pagination
          page={page}
          totalPages={totalPages}
          onPageChange={onPageChange}
        />
      )}
    </>
  )
}

/** One excluded/unparsed row with raw cells + 捞回 button. */
function ExcludedRow({
  row,
  onRestore,
  isRestoring,
}: {
  row: FlowRecordItem
  onRestore: () => void
  isRestoring: boolean
}) {
  const rawCells = row.raw_payload?.cells ?? []
  return (
    <div className="flex items-start gap-4 p-4 transition-colors hover:bg-ink-300">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-ink-700">#{row.id}</span>
          <span className="font-mono text-xs text-ink-700">
            行 {row.row_index}
          </span>
          {row.channel && (
            <span className="rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-200 px-1.5 py-0.5 text-[11px] text-ink-700">
              {row.channel}
            </span>
          )}
          <span className="rounded-[var(--radius-DEFAULT)] bg-ink-400 px-1.5 py-0.5 text-[11px] text-ink-900">
            {row.record_type === "excluded" ? "非流水表" : "噪音行"}
          </span>
        </div>
        <div className="mt-2 font-mono text-xs text-ink-700">
          {row.exclude_reason || "—"}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {rawCells.map((cell, idx) => (
            <span
              key={idx}
              className="rounded-[var(--radius-DEFAULT)] bg-ink-200 px-1.5 py-0.5 font-mono text-xs text-ink-900"
            >
              {cell || "（空）"}
            </span>
          ))}
          {rawCells.length === 0 && (
            <span className="text-xs text-ink-700">无原始数据</span>
          )}
        </div>
      </div>
      <Button
        variant="tertiary"
        size="sm"
        onClick={onRestore}
        disabled={isRestoring || row.status === "restored"}
      >
        <RotateCcw className="size-3.5" />
        {row.status === "restored" ? "已捞回" : "捞回"}
      </Button>
    </div>
  )
}

/** Sub-tab toggle (excluded / unparsed) — active gets bold + bg highlight. */
function SubTabButton({
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

/** Minimal grayscale pagination — current page is black bg white text. */
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

// Re-export RecordType for downstream (keeps the type reachable from the route
// module if needed). No runtime cost.
export type { RecordType }
