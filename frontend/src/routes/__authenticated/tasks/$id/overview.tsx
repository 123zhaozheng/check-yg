import { createFileRoute } from "@tanstack/react-router"
import { Card, CardContent } from "@/components/ui/card"

/**
 * 概览 /tasks/:id/overview (docs §C1).
 *
 * Title/description are NOT repeated here — the layout shell ($id.tsx) already
 * renders the task PageHeader, and the tab nav highlights 概览. Only a one-line
 * placeholder body is shown until the S-slice fills the timeline + KPIs.
 */
export const Route = createFileRoute("/__authenticated/tasks/$id/overview")({
  component: () => (
    <Card>
      <CardContent className="p-6">
        <p className="text-sm text-ink-700">
          任务全景：数据齐备度、整体进度、关键事件时间线、下一步入口。
        </p>
      </CardContent>
    </Card>
  ),
})
