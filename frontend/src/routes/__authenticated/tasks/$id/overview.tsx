import { createFileRoute } from "@tanstack/react-router"
import { TabPlaceholder } from "@/components/layout/tab-placeholder"

/** 概览 /tasks/:id/overview (docs §C1). Placeholder — S-slice fills timeline + KPIs. */
export const Route = createFileRoute("/__authenticated/tasks/$id/overview")({
  component: () => (
    <TabPlaceholder
      title="概览"
      description="任务全景：数据齐备度、整体进度、关键事件时间线、下一步入口。"
    />
  ),
})
