import { createFileRoute } from "@tanstack/react-router"
import { TabPlaceholder } from "@/components/layout/tab-placeholder"

/** 数据导入 /tasks/:id/import (docs §C2). Placeholder — S4 wires upload + parse status. */
export const Route = createFileRoute("/__authenticated/tasks/$id/import")({
  component: () => (
    <TabPlaceholder
      title="数据导入"
      description="按渠道上传流水 PDF/Excel，查看每个文件的解析状态。"
    />
  ),
})
