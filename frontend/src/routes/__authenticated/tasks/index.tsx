import * as React from "react"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react"

import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { StatusPill } from "@/components/ui/status-pill"
import { NewTaskDialog } from "@/components/tasks/new-task-dialog"
import { useArchiveTask, useTaskList } from "@/hooks/use-tasks"
import { cn } from "@/lib/utils"
import type { TaskItem, TaskListParams } from "@/lib/api"

/**
 * 审查任务列表 /tasks (docs §B2).
 *
 * 顶部筛选条: Tab(全部/进行中/已完成/已归档) + 创建时间范围 + 搜索框.
 * 任务表: 任务名 / 员工工号 / 涉及渠道 / 创建人 / 当前阶段(灰阶胶囊) /
 *        状态(点+文字) / 创建时间 / 操作(查看 + 归档).
 * 分页: 当前页黑底白字方块.
 * 新建任务: 顶部黑底主按钮 → Dialog (创建后跳数据导入 Tab).
 */
export const Route = createFileRoute("/__authenticated/tasks/")({
  component: TasksPage,
})

type TabKey = "all" | "running" | "completed" | "archived"

const TABS: { key: TabKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "running", label: "进行中" },
  { key: "completed", label: "已完成" },
  { key: "archived", label: "已归档" },
]

const PAGE_SIZE = 10

function TasksPage() {
  const navigate = useNavigate()
  const archiveTask = useArchiveTask()

  const [tab, setTab] = React.useState<TabKey>("all")
  const [search, setSearch] = React.useState("")
  const [createdAfter, setCreatedAfter] = React.useState("")
  const [createdBefore, setCreatedBefore] = React.useState("")
  const [page, setPage] = React.useState(1)
  const [dialogOpen, setDialogOpen] = React.useState(false)

  // Debounce the search input so typing doesn't fire a request per keystroke.
  const [debouncedSearch, setDebouncedSearch] = React.useState("")
  React.useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  // Build the query params from the active filters. `archived` only flips to
  // true on the archived tab; other tabs always look at non-archived rows.
  const params: TaskListParams = React.useMemo(() => {
    const p: TaskListParams = {
      page,
      page_size: PAGE_SIZE,
      search: debouncedSearch || undefined,
      created_after: createdAfter ? `${createdAfter}T00:00:00` : undefined,
      created_before: createdBefore ? `${createdBefore}T23:59:59` : undefined,
    }
    if (tab === "archived") {
      p.archived = true
    } else {
      p.archived = false
      if (tab === "running") p.status_filter = "running"
      else if (tab === "completed") p.status_filter = "completed"
    }
    return p
  }, [tab, page, debouncedSearch, createdAfter, createdBefore])

  // Reset to page 1 when the date filters change.
  React.useEffect(() => {
    setPage(1)
  }, [createdAfter, createdBefore])

  const { data, isLoading, isError } = useTaskList(params)
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function handleArchive(taskId: number) {
    void archiveTask.mutate(taskId)
  }

  function handleView(taskId: number) {
    void navigate({ to: `/tasks/${taskId}` })
  }

  return (
    <>
      <PageHeader
        title="审查任务"
        description="检索、筛选并进入历史审查任务。"
        actions={
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            新建任务
          </Button>
        }
      />

      {/* Filter bar */}
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
          {/* Status tabs */}
          <div className="flex space-x-1 border-b border-ink-400 pb-px">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => {
                  setTab(t.key)
                  setPage(1)
                }}
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

          {/* Date range + search */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 border-b border-ink-500 pb-1 focus-within:border-ink-900">
              <input
                type="date"
                value={createdAfter}
                onChange={(e) => setCreatedAfter(e.target.value)}
                aria-label="创建时间起"
                className="w-32 border-none bg-transparent p-0 font-mono text-sm text-ink-900 focus:ring-0"
              />
              <span className="text-ink-500">–</span>
              <input
                type="date"
                value={createdBefore}
                onChange={(e) => setCreatedBefore(e.target.value)}
                aria-label="创建时间止"
                className="w-32 border-none bg-transparent p-0 font-mono text-sm text-ink-900 focus:ring-0"
              />
            </div>
            <div className="relative w-64">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-600" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索任务名…"
                className="h-9 w-full rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 pl-8 pr-3 text-sm text-ink-900 placeholder:text-ink-600 focus:border-ink-900 focus:outline-none"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Task table */}
      <Card>
        <CardContent className="p-0">
          <table className="w-full border-collapse text-left">
            <thead className="border-b border-ink-400 bg-ink-200 text-xs font-bold uppercase tracking-wider text-ink-700">
              <tr>
                <th className="px-4 py-3 font-bold">任务名</th>
                <th className="px-4 py-3 font-bold">员工工号</th>
                <th className="px-4 py-3 font-bold">渠道</th>
                <th className="px-4 py-3 font-bold">创建人</th>
                <th className="px-4 py-3 font-bold">阶段</th>
                <th className="px-4 py-3 font-bold">状态</th>
                <th className="px-4 py-3 font-bold">创建时间</th>
                <th className="px-4 py-3 text-right font-bold">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-400 text-sm text-ink-900">
              {isLoading && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-ink-600">
                    加载中…
                  </td>
                </tr>
              )}
              {isError && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-ink-600">
                    任务列表加载失败，请稍后重试。
                  </td>
                </tr>
              )}
              {!isLoading && !isError && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-ink-600">
                    暂无任务。
                  </td>
                </tr>
              )}
              {items.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  onView={() => handleView(task.id)}
                  onArchive={() => handleArchive(task.id)}
                />
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t border-ink-400 px-6 py-4">
            <div className="text-sm text-ink-700">
              共 <span className="font-medium text-ink-900">{total}</span> 条 · 第{" "}
              <span className="font-medium text-ink-900">{page}</span> / {totalPages} 页
            </div>
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
          </div>
        </CardContent>
      </Card>

      <NewTaskDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  )
}

/** One task row. Stage maps to a grayscale StatusPill; status is a dot + text. */
function TaskRow({
  task,
  onView,
  onArchive,
}: {
  task: TaskItem
  onView: () => void
  onArchive: () => void
}) {
  const stage = stageFromStatus(task.status)
  const statusView = statusViewFromStatus(task.status)
  const channels = formatChannels(task.expected_channels)

  return (
    <tr className="transition-colors hover:bg-ink-300">
      <td className="px-4 py-3 font-medium text-ink-900">
        <button onClick={onView} className="text-left hover:underline">
          {task.title}
        </button>
      </td>
      <td className="px-4 py-3 font-mono text-xs text-ink-700">
        {task.employee_id ?? "—"}
      </td>
      <td className="px-4 py-3 text-xs text-ink-700">{channels}</td>
      <td className="px-4 py-3 text-xs text-ink-700">#{task.owner_id}</td>
      <td className="px-4 py-3">
        <StatusPill tone={stage.tone}>{stage.label}</StatusPill>
      </td>
      <td className="px-4 py-3">
        <span className="flex items-center gap-2">
          <span
            className={cn(
              "size-2 rounded-full",
              statusView.active ? "bg-ink-900" : "border border-ink-700",
            )}
          />
          <span className={statusView.active ? "text-ink-900" : "text-ink-700"}>
            {statusView.label}
          </span>
        </span>
      </td>
      <td className="px-4 py-3 font-mono text-xs text-ink-700">
        {formatDate(task.created_at)}
      </td>
      <td className="px-4 py-3 text-right">
        <span className="inline-flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onView}>
            查看
          </Button>
          {!task.archived && (
            <Button variant="ghost" size="sm" onClick={onArchive}>
              归档
            </Button>
          )}
        </span>
      </td>
    </tr>
  )
}

/** Compact page-number pagination; current page is a solid black square. */
function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
}) {
  if (totalPages <= 1) return null

  // Build a windowed page list: first, last, current ±1, with an ellipsis gap.
  const pages: (number | "…")[] = []
  const add = (n: number | "…") => {
    if (pages[pages.length - 1] !== n) pages.push(n)
  }
  add(1)
  for (let i = page - 1; i <= page + 1; i++) {
    if (i > 1 && i < totalPages) add(i)
  }
  if (totalPages > 1) add(totalPages)

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => onChange(Math.max(1, page - 1))}
        disabled={page <= 1}
        className="p-1 text-ink-700 transition-colors hover:text-ink-900 disabled:opacity-40"
        aria-label="上一页"
      >
        <ChevronLeft className="size-4" />
      </button>
      {pages.map((p, idx) =>
        p === "…" ? (
          <span key={`gap-${idx}`} className="px-2 text-ink-600">
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onChange(p)}
            className={cn(
              "flex size-8 items-center justify-center font-mono text-sm transition-colors",
              p === page
                ? "bg-ink-900 text-ink-100"
                : "text-ink-900 hover:bg-ink-300",
            )}
          >
            {p}
          </button>
        ),
      )}
      <button
        onClick={() => onChange(Math.min(totalPages, page + 1))}
        disabled={page >= totalPages}
        className="p-1 text-ink-700 transition-colors hover:text-ink-900 disabled:opacity-40"
        aria-label="下一页"
      >
        <ChevronRight className="size-4" />
      </button>
    </div>
  )
}

/** Map task.status → a grayscale stage pill tone + label (导入/清洗/分析/报告). */
function stageFromStatus(
  status: string,
): { tone: "pending" | "in-progress" | "done" | "reported" | "failed"; label: string } {
  switch (status) {
    case "draft":
      return { tone: "pending", label: "待导入" }
    case "running":
      return { tone: "in-progress", label: "清洗中" }
    case "paused":
      return { tone: "pending", label: "已暂停" }
    case "completed":
      return { tone: "done", label: "已完成" }
    case "failed":
      return { tone: "failed", label: "失败" }
    case "cancelled":
      return { tone: "pending", label: "已取消" }
    default:
      return { tone: "pending", label: "待导入" }
  }
}

/** Map task.status → a status dot + label (active/pending/completed). */
function statusViewFromStatus(status: string): { active: boolean; label: string } {
  switch (status) {
    case "running":
      return { active: true, label: "进行中" }
    case "completed":
      return { active: true, label: "已完成" }
    case "draft":
      return { active: false, label: "待开始" }
    case "paused":
      return { active: false, label: "已暂停" }
    case "failed":
      return { active: true, label: "失败" }
    case "cancelled":
      return { active: false, label: "已取消" }
    default:
      return { active: false, label: "待开始" }
  }
}

/** Render expected_channels (e.g. ["银行","支付"]) as a comma list. */
function formatChannels(channels?: string[] | null): string {
  if (!channels || channels.length === 0) return "—"
  return channels.join("、")
}

/** Format an ISO datetime as "YYYY-MM-DD HH:mm" for the table cell. */
function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
