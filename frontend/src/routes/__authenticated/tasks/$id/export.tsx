import { createFileRoute } from "@tanstack/react-router"
import { TabPlaceholder } from "@/components/layout/tab-placeholder"

/** 导出 /tasks/:id/export (docs §C6). Placeholder — S8 wires export + history. */
export const Route = createFileRoute("/__authenticated/tasks/$id/export")({
  component: () => (
    <TabPlaceholder
      title="导出"
      description="将报告与原始/标准化数据导出为多种格式，供归档与线下流转。"
    />
  ),
})
