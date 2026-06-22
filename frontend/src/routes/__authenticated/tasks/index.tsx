import { createFileRoute } from "@tanstack/react-router"
import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { StatusPill } from "@/components/ui/status-pill"
import { Plus, Search } from "lucide-react"

/**
 * 审查任务 /tasks (docs §B2).
 * Placeholder — S3 wires filter bar, task table, batch operations, pagination.
 */
export const Route = createFileRoute("/__authenticated/tasks/")({
  component: TasksPage,
})

function TasksPage() {
  return (
    <>
      <PageHeader
        title="审查任务"
        description="检索、筛选并进入历史审查任务。"
        actions={
          <Button size="sm">
            <Plus className="size-4" />
            新建任务
          </Button>
        }
      />

      {/* Filter bar placeholder */}
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-600" />
            <input
              type="text"
              placeholder="搜索任务名 / 员工标识…"
              className="h-9 w-full rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 pl-8 pr-3 text-sm text-ink-900 placeholder:text-ink-600 focus:border-ink-900 focus:outline-none"
            />
          </div>
          <select className="h-9 rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-3 text-sm text-ink-900 focus:border-ink-900 focus:outline-none">
            <option>全部状态</option>
            <option>进行中</option>
            <option>已完成</option>
            <option>已归档</option>
          </select>
          <select className="h-9 rounded-[var(--radius-DEFAULT)] border border-ink-400 bg-ink-100 px-3 text-sm text-ink-900 focus:border-ink-900 focus:outline-none">
            <option>全部阶段</option>
            <option>导入</option>
            <option>清洗</option>
            <option>分析</option>
            <option>报告</option>
          </select>
        </CardContent>
      </Card>

      {/* Task table */}
      <Card>
        <CardContent className="p-0">
          <div className="grid grid-cols-12 gap-4 border-b border-ink-400 bg-ink-300 px-6 py-3 text-xs font-bold uppercase tracking-wider text-ink-700">
            <div className="col-span-3">任务名</div>
            <div className="col-span-2">员工标识</div>
            <div className="col-span-1">渠道数</div>
            <div className="col-span-2">当前阶段</div>
            <div className="col-span-2">状态</div>
            <div className="col-span-2 text-right">操作</div>
          </div>
          <div className="divide-y divide-ink-400">
            {TASK_ROWS.map((t) => (
              <div
                key={t.id}
                className="grid grid-cols-12 items-center gap-4 px-6 py-4 text-sm transition-colors hover:bg-ink-300"
              >
                <div className="col-span-3 min-w-0 truncate font-medium text-ink-900">
                  {t.name}
                </div>
                <div className="col-span-2 truncate font-mono text-xs text-ink-700">
                  {t.employee}
                </div>
                <div className="col-span-1 font-mono text-xs text-ink-700">
                  {t.channels}
                </div>
                <div className="col-span-2">
                  <StatusPill tone={t.stageTone}>{t.stage}</StatusPill>
                </div>
                <div className="col-span-2">
                  <StatusPill tone={t.statusTone}>{t.status}</StatusPill>
                </div>
                <div className="col-span-2 flex justify-end gap-2">
                  <Button variant="secondary" size="sm">
                    查看
                  </Button>
                  <Button variant="ghost" size="sm">
                    归档
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </>
  )
}

const TASK_ROWS = [
  {
    id: "1",
    name: "2026-06 张某某流水审查",
    employee: "工号 ZS-0421",
    channels: "4",
    stage: "清洗中",
    stageTone: "in-progress" as const,
    status: "进行中",
    statusTone: "in-progress" as const,
  },
  {
    id: "2",
    name: "2026-05 李某某季度审查",
    employee: "工号 LS-1108",
    channels: "3",
    stage: "待导入",
    stageTone: "pending" as const,
    status: "进行中",
    statusTone: "in-progress" as const,
  },
  {
    id: "3",
    name: "2026-05 王某某专项审查",
    employee: "工号 WW-2035",
    channels: "2",
    stage: "已报告",
    stageTone: "reported" as const,
    status: "已完成",
    statusTone: "done" as const,
  },
]
