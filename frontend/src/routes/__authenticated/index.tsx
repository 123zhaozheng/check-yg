import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { ArrowDown, ArrowUp, Download, Plus, RefreshCw } from "lucide-react"

import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { StatusPill } from "@/components/ui/status-pill"
import {
  useDashboard,
  useInvalidateDashboard,
  type DashboardTodoTask,
  type DashboardTodoType,
} from "@/hooks/use-dashboard"
import { cn } from "@/lib/utils"

/**
 * 工作台 / (docs §B1 Dashboard, stitch_/dashboard/code.html).
 *
 * Monochrome landing page — KPI numbers via font size/weight (never hue),
 * 同比 ↑/↓ in grayscale (never red/green), stage pills reuse the grayscale
 * StatusPill, progress bars are grayscale gradients (never colored).
 *
 * Sections: 4 KPI cards → in-progress task table (clickable rows → /tasks/{id})
 * → recent reports + pending actions split.
 */
export const Route = createFileRoute("/__authenticated/")({
  component: DashboardPage,
})

function DashboardPage() {
  const navigate = useNavigate()
  const invalidateDashboard = useInvalidateDashboard()
  // dataUpdatedAt is the wall-clock time of the last successful fetch (TanStack
  // Query tracks it). Drives the "上次同步" header so it moves on every
  // refresh / passive poll, instead of staying pinned to a stale task row.
  const { data, dataUpdatedAt, isLoading, isFetching } = useDashboard()

  const lastSync = formatLastSync(dataUpdatedAt)

  // 待办任务块（按 latest_todo_at 降序，后端已截 8）。`showTodosCard` 控制卡片渲染
  // 与底部 grid 列数：加载中保留卡片走 skeleton；加载完成且确为空则整块隐藏，
  // 让"最近报告"独占整行。
  const todos = data?.todos ?? []
  const showTodosCard = isLoading || todos.length > 0

  return (
    <>
      <PageHeader
        title="工作台"
        actions={
          <>
            <span className="hidden text-xs text-ink-600 sm:inline">
              上次同步：{lastSync}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => invalidateDashboard()}
              disabled={isFetching}
            >
              <RefreshCw className={cn("size-4", isFetching && "animate-spin")} />
              刷新
            </Button>
            <Button size="sm" onClick={() => navigate({ to: "/tasks" })}>
              <Plus className="size-4" />
              新建审查
            </Button>
          </>
        }
      />

      {/* KPI cards — 4 across on lg, value via font size/weight only. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="进行中任务数"
          value={isLoading ? "—" : String(data?.kpis.active_tasks ?? 0)}
          icon={<ArrowUp className="size-3" />}
          delta="较上月"
          barPct={35}
        />
        <KpiCard
          label="本月已完成审查"
          value={isLoading ? "—" : String(data?.kpis.monthly_completed ?? 0)}
          icon={<ArrowUp className="size-3" />}
          delta="较上月"
        />
        <KpiCard
          label="待处理告警数"
          value={isLoading ? "—" : String(data?.kpis.pending_alerts ?? 0)}
          icon={<ArrowUp className="size-3" />}
          delta="较上周"
          barPct={75}
        />
        <KpiCard
          label="平均审查耗时"
          value={isLoading ? "—" : formatHours(data?.kpis.avg_audit_hours ?? 0)}
          icon={<ArrowDown className="size-3" />}
          delta="较上月"
        />
      </div>

      {/* In-progress task table */}
      <Card className="mt-6">
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b border-ink-400 px-6 py-4">
            <h2 className="font-sans text-base font-semibold text-ink-900">
              进行中任务
            </h2>
            <Button
              variant="tertiary"
              size="sm"
              onClick={() => navigate({ to: "/tasks" })}
            >
              查看全部
            </Button>
          </div>

          {/* Header row */}
          <div className="hidden grid-cols-12 gap-4 border-b border-ink-400 bg-ink-300 px-6 py-3 text-xs font-bold uppercase tracking-wider text-ink-700 md:grid">
            <div className="col-span-4">任务名</div>
            <div className="col-span-2">工号</div>
            <div className="col-span-2">当前阶段</div>
            <div className="col-span-2">进度</div>
            <div className="col-span-2 text-right">更新时间</div>
          </div>

          {isLoading ? (
            <DashboardSkeleton rows={4} />
          ) : !data || data.in_progress_tasks.length === 0 ? (
            <EmptyState
              message="暂无进行中的审查任务。"
              cta="新建审查"
              onCta={() => navigate({ to: "/tasks" })}
            />
          ) : (
            <div className="divide-y divide-ink-400">
              {data.in_progress_tasks.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => navigate({ to: `/tasks/${t.id}` })}
                  className="grid w-full grid-cols-1 items-center gap-3 px-6 py-4 text-left transition-colors hover:bg-ink-300 md:grid-cols-12 md:gap-4"
                >
                  <div className="min-w-0 md:col-span-4">
                    <div className="truncate font-medium text-ink-900">
                      {t.title}
                    </div>
                    <div className="truncate font-mono text-xs text-ink-600 md:hidden">
                      {t.stage} · {t.progress}%
                    </div>
                  </div>
                  <div className="hidden font-mono text-xs text-ink-600 md:col-span-2 md:block">
                    {t.employee_id || "—"}
                  </div>
                  <div className="hidden md:col-span-2 md:block">
                    <StatusPill tone={stageTone(t.stage)}>{t.stage}</StatusPill>
                  </div>
                  <div className="hidden items-center gap-2 md:col-span-2 md:flex">
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink-400">
                      <div
                        className="h-full bg-ink-900"
                        style={{ width: `${clampPct(t.progress)}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs text-ink-600">
                      {t.progress}%
                    </span>
                  </div>
                  <div className="hidden text-right font-mono text-xs text-ink-600 md:col-span-2 md:block">
                    {formatRelative(t.updated_at)}
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bottom split: recent reports + pending actions.
          When there are no todo tasks, the "待我处理" card is hidden entirely
          and "最近报告" stretches to fill the row (grid collapses to 1 col). */}
      <div
        className={cn(
          "mt-6 grid grid-cols-1 gap-4 pb-8",
          showTodosCard ? "lg:grid-cols-2" : "lg:grid-cols-1",
        )}
      >
        <RecentReportsCard
          isLoading={isLoading}
          reports={data?.recent_reports ?? []}
          onArchive={() => navigate({ to: "/tasks" })}
        />
        {showTodosCard && (
          <PendingActionsCard
            isLoading={isLoading}
            todos={todos}
            onAction={(taskId, suffix) =>
              navigate({ to: `/tasks/${taskId}/${suffix}` })
            }
          />
        )}
      </div>
    </>
  )
}

/* -------------------------------------------------------------------------- */
/* KPI card                                                                   */
/* -------------------------------------------------------------------------- */

function KpiCard({
  label,
  value,
  icon,
  delta,
  barPct,
}: {
  label: string
  value: string
  icon: React.ReactNode
  delta: string
  barPct?: number
}) {
  return (
    <Card className="relative overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-ink-600">
            {label}
          </h3>
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="font-mono text-3xl font-bold leading-tight tracking-tight text-ink-900">
            {value}
          </span>
          <span className="flex items-center text-xs font-medium text-ink-600">
            {icon}
            {delta}
          </span>
        </div>
      </CardContent>
      {barPct !== undefined && (
        <div className="absolute bottom-0 left-0 h-1 w-full bg-ink-400">
          <div
            className="h-full bg-ink-900"
            style={{ width: `${clampPct(barPct)}%` }}
          />
        </div>
      )}
    </Card>
  )
}

/* -------------------------------------------------------------------------- */
/* Recent reports                                                             */
/* -------------------------------------------------------------------------- */

function RecentReportsCard({
  isLoading,
  reports,
  onArchive,
}: {
  isLoading: boolean
  reports: { id: number; task_id: number; task_title: string; created_at: string }[]
  onArchive: () => void
}) {
  const navigate = useNavigate()
  return (
    <Card>
      <CardContent className="flex h-full flex-col p-0">
        <div className="flex items-center justify-between border-b border-ink-400 px-6 py-4">
          <h2 className="font-sans text-base font-semibold text-ink-900">
            最近报告
          </h2>
        </div>
        {isLoading ? (
          <DashboardSkeleton rows={3} />
        ) : reports.length === 0 ? (
          <EmptyState message="暂无最近生成的报告。" />
        ) : (
          <div className="flex-1 divide-y divide-ink-400">
            {reports.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => navigate({ to: `/tasks/${r.task_id}/report` })}
                className="group flex w-full items-center justify-between gap-4 px-6 py-4 text-left transition-colors hover:bg-ink-300"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium text-ink-900 group-hover:underline group-hover:underline-offset-2">
                    {r.task_title}
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-ink-600">
                    报告 #{r.id} · {formatRelative(r.created_at)}
                  </div>
                </div>
                <Download className="size-4 shrink-0 text-ink-600 opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            ))}
          </div>
        )}
        <div className="border-t border-ink-400 px-6 py-3 text-center">
          <Button variant="tertiary" size="sm" onClick={onArchive}>
            查看归档
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

/* -------------------------------------------------------------------------- */
/* Pending actions                                                            */
/* -------------------------------------------------------------------------- */

/**
 * 待办类型 → 路由 suffix 映射。路由是前端职责，后端只给 `type`，避免跨层耦合。
 * 与 prd 的四类待办跳转目标一一对应。
 */
const TODO_ROUTE_SUFFIX: Record<DashboardTodoType, string> = {
  balance_check: "clean",
  keyword: "keyword-review",
  analysis: "analyze",
  report_finalize: "report",
}

function PendingActionsCard({
  isLoading,
  todos,
  onAction,
}: {
  isLoading: boolean
  todos: DashboardTodoTask[]
  onAction: (taskId: number, suffix: string) => void
}) {
  return (
    <Card>
      <CardContent className="flex h-full flex-col p-0">
        <div className="flex items-center justify-between border-b border-ink-400 px-6 py-4">
          <h2 className="font-sans text-base font-semibold text-ink-900">
            待我处理
          </h2>
          {!isLoading && todos.length > 0 && (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-ink-900 px-1.5 text-xs font-bold text-ink-100">
              {todos.length}
            </span>
          )}
        </div>
        {isLoading ? (
          <DashboardSkeleton rows={3} />
        ) : (
          <div className="flex-1 divide-y divide-ink-400">
            {todos.map((todo) => (
              <div key={todo.task_id} className="px-6 py-4">
                <h3 className="truncate font-medium text-ink-900">
                  {todo.title}
                </h3>
                <ul className="mt-2 flex flex-col gap-1.5">
                  {todo.items.map((item) => (
                    <li
                      key={item.type}
                      className="flex items-center justify-between gap-3"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="size-2 shrink-0 rounded-full bg-ink-900" />
                        <span className="truncate text-sm text-ink-700">
                          {item.label}
                          {item.count != null && item.count > 0 && (
                            <span className="font-mono text-xs text-ink-600">
                              {" "}
                              （{item.count} 条）
                            </span>
                          )}
                        </span>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          onAction(todo.task_id, TODO_ROUTE_SUFFIX[item.type])
                        }
                        className="shrink-0"
                      >
                        {item.action}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* -------------------------------------------------------------------------- */
/* Loading / empty states                                                     */
/* -------------------------------------------------------------------------- */

function DashboardSkeleton({ rows }: { rows: number }) {
  return (
    <div className="divide-y divide-ink-400">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="px-6 py-4">
          <div className="h-4 w-1/2 animate-pulse bg-ink-300" />
          <div className="mt-2 h-3 w-1/4 animate-pulse bg-ink-300" />
        </div>
      ))}
    </div>
  )
}

function EmptyState({
  message,
  cta,
  onCta,
}: {
  message: string
  cta?: string
  onCta?: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <p className="text-sm text-ink-600">{message}</p>
      {cta && onCta && (
        <Button size="sm" onClick={onCta}>
          {cta}
        </Button>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

/** Map backend stage label → StatusPill grayscale tone. */
function stageTone(stage: string): React.ComponentProps<typeof StatusPill>["tone"] {
  switch (stage) {
    case "已完成":
    case "清洗完成":
      return "done"
    case "报告生成":
      return "reported"
    case "清洗中":
    case "分析中":
      return "in-progress"
    case "失败":
      return "failed"
    case "待导入":
    case "已暂停":
    case "已取消":
    default:
      return "pending"
  }
}

function clampPct(pct: number): number {
  if (!Number.isFinite(pct)) return 0
  return Math.max(0, Math.min(100, Math.round(pct)))
}

function formatHours(hours: number): string {
  if (hours <= 0) return "—"
  if (hours < 1) return `${Math.round(hours * 60)}分钟`
  return `${hours.toFixed(1)}小时`
}

function formatLastSync(dataUpdatedAt?: number): string {
  if (!dataUpdatedAt) return "—"
  return formatRelative(new Date(dataUpdatedAt).toISOString())
}

function formatRelative(iso: string): string {
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return "—"
  const diffMs = Date.now() - then.getTime()
  const sec = Math.round(diffMs / 1000)
  if (sec < 60) return "刚刚"
  const min = Math.round(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.round(hr / 24)
  if (day < 30) return `${day} 天前`
  // Fallback to YYYY-MM-DD for older entries.
  return then.toISOString().slice(0, 10)
}
