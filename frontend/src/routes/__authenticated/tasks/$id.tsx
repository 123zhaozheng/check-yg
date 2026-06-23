import {
  createFileRoute,
  Link,
  Outlet,
  useParams,
  useLocation,
} from "@tanstack/react-router"
import { PageHeader } from "@/components/layout/page-header"
import { Card, CardContent } from "@/components/ui/card"
import { StatusPill } from "@/components/ui/status-pill"
import { cn } from "@/lib/utils"

/**
 * 任务详情壳 /tasks/:id (docs §C0).
 * Renders the constant task header (name + employee + review period + stage
 * progress bar + status pill) and the sub-nav. Each tab is a child route.
 *
 *   1 数据导入   → /tasks/:id/import   (index redirect)
 *   2 清洗标准化 → /tasks/:id/clean
 *   3 关键词审查 → /tasks/:id/keyword-review
 *   4 AI 分析    → /tasks/:id/analyze
 *   5 审查报告   → /tasks/:id/report
 *   6 导出       → /tasks/:id/export
 *
 * 06-23-tab: 概览 tab 已删，/tasks/:id 落到「数据导入」；顶部进度条 5 段含「关键词」。
 */
export const Route = createFileRoute("/__authenticated/tasks/$id")({
  component: TaskDetailShell,
})

const TABS = [
  { segment: "import", label: "数据导入" },
  { segment: "clean", label: "清洗标准化" },
  { segment: "keyword-review", label: "关键词审查" },
  { segment: "analyze", label: "AI 分析" },
  { segment: "report", label: "审查报告" },
  { segment: "export", label: "导出" },
] as const

const STAGES = [
  { label: "导入", tone: "done" as const },
  { label: "清洗", tone: "in-progress" as const },
  { label: "关键词", tone: "pending" as const },
  { label: "分析", tone: "pending" as const },
  { label: "报告", tone: "pending" as const },
]

function TaskDetailShell() {
  const { id } = useParams({ from: "/__authenticated/tasks/$id" })
  const location = useLocation()

  return (
    <>
      <PageHeader
        title={`2026-06 任务 ${id}`}
        description="员工 工号 ZS-0421 · 审查期间 2026-01 至 2026-06"
        actions={<StatusPill tone="in-progress">进行中</StatusPill>}
      />

      {/* Stage progress bar — luminance gradient replaces color progress. */}
      <Card className="mb-4">
        <CardContent className="p-5">
          <div className="flex items-center gap-2">
            {STAGES.map((s, i) => (
              <div key={s.label} className="flex flex-1 items-center gap-2">
                <div
                  className={cn(
                    "h-2 flex-1 rounded-[var(--radius-DEFAULT)]",
                    s.tone === "done" && "bg-ink-900",
                    s.tone === "in-progress" && "bg-ink-500",
                    s.tone === "pending" && "bg-ink-300",
                  )}
                />
                <span
                  className={cn(
                    "text-xs",
                    s.tone === "in-progress"
                      ? "font-bold text-ink-900"
                      : "text-ink-600",
                  )}
                >
                  {s.label}
                </span>
                {i < STAGES.length - 1 && (
                  <span className="text-ink-500">›</span>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Tab navigation */}
      <div className="mb-4 flex items-center gap-6 border-b border-ink-400">
        {TABS.map((tab) => {
          const tabPath = `/tasks/${id}/${tab.segment}`
          const isActive = location.pathname === tabPath
          return (
            <Link
              key={tab.segment}
              to={tabPath}
              className={cn(
                "relative whitespace-nowrap pb-3 pt-1 text-sm transition-colors",
                isActive
                  ? "font-bold text-ink-900"
                  : "text-ink-700 hover:text-ink-900",
              )}
            >
              {tab.label}
              {isActive && (
                <span className="absolute inset-x-0 -bottom-px h-0.5 bg-ink-900" />
              )}
            </Link>
          )
        })}
      </div>

      {/* Tab content (child route) */}
      <Outlet />
    </>
  )
}
