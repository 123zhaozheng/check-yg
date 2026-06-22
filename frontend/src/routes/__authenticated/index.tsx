import { createFileRoute } from "@tanstack/react-router"
import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { StatusPill } from "@/components/ui/status-pill"
import { Plus, RefreshCw } from "lucide-react"

/**
 * 工作台 / (docs §B1 Dashboard).
 * Placeholder — S2 wires KPI cards, in-progress task list, recent reports,
 * and pending alerts. Layout follows the design: 4 KPI cards → in-progress
 * task list → recent reports + pending work.
 */
export const Route = createFileRoute("/__authenticated/")({
  component: DashboardPage,
})

function KpiCard({ label, value, delta }: { label: string; value: string; delta?: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="text-xs font-semibold uppercase tracking-widest text-ink-600">
          {label}
        </div>
        <div className="mt-3 font-mono text-3xl font-bold leading-tight text-ink-900">
          {value}
        </div>
        {delta && <div className="mt-2 text-xs text-ink-700">{delta}</div>}
      </CardContent>
    </Card>
  )
}

function DashboardPage() {
  return (
    <>
      <PageHeader
        title="工作台"
        description="实时审查进展与待办队列。"
        actions={
          <>
            <Button variant="secondary" size="sm">
              <RefreshCw className="size-4" />
              刷新
            </Button>
            <Button size="sm">
              <Plus className="size-4" />
              新建任务
            </Button>
          </>
        }
      />

      {/* KPI cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="进行中任务数" value="12" delta="↑ 较上月 +3" />
        <KpiCard label="本月已完成审查" value="48" delta="↓ 较上月 -2" />
        <KpiCard label="待处理告警数" value="7" delta="↑ 较上周 +1" />
        <KpiCard label="平均审查耗时" value="3.2天" delta="↓ 较上月 -0.4天" />
      </div>

      {/* In-progress task list */}
      <Card className="mt-6">
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b border-ink-400 px-6 py-4">
            <h2 className="font-sans text-lg font-semibold text-ink-900">
              进行中任务
            </h2>
            <span className="text-xs text-ink-600">最近更新：今日 08:42</span>
          </div>
          <div className="divide-y divide-ink-400">
            {SAMPLE_TASKS.map((t) => (
              <div
                key={t.id}
                className="grid grid-cols-12 items-center gap-4 px-6 py-4 text-sm transition-colors hover:bg-ink-300"
              >
                <div className="col-span-4 min-w-0">
                  <div className="truncate font-medium text-ink-900">
                    {t.name}
                  </div>
                  <div className="truncate font-mono text-xs text-ink-600">
                    {t.employee}
                  </div>
                </div>
                <div className="col-span-2 font-mono text-xs text-ink-700">
                  {t.channels}
                </div>
                <div className="col-span-2">
                  <StatusPill tone={t.tone}>{t.stage}</StatusPill>
                </div>
                <div className="col-span-2 font-mono text-xs text-ink-700">
                  {t.progress}
                </div>
                <div className="col-span-2 text-right font-mono text-xs text-ink-600">
                  {t.updated}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </>
  )
}

const SAMPLE_TASKS = [
  {
    id: "1",
    name: "2026-06 张某某流水审查",
    employee: "工号 ZS-0421",
    channels: "4 个渠道",
    stage: "清洗中",
    tone: "in-progress" as const,
    progress: "45%",
    updated: "10 分钟前",
  },
  {
    id: "2",
    name: "2026-05 李某某季度审查",
    employee: "工号 LS-1108",
    channels: "3 个渠道",
    stage: "待解析",
    tone: "pending" as const,
    progress: "10%",
    updated: "1 小时前",
  },
  {
    id: "3",
    name: "2026-05 王某某专项审查",
    employee: "工号 WW-2035",
    channels: "2 个渠道",
    stage: "已报告",
    tone: "reported" as const,
    progress: "100%",
    updated: "昨日 16:20",
  },
]
