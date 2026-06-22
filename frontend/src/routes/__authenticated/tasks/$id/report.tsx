import { createFileRoute } from "@tanstack/react-router"
import { TabPlaceholder } from "@/components/layout/tab-placeholder"

/** 审查报告 /tasks/:id/report (docs §C5). Placeholder — S7 wires report + review + finalize. */
export const Route = createFileRoute("/__authenticated/tasks/$id/report")({
  component: () => (
    <TabPlaceholder
      title="审查报告"
      description="将分析结论汇总为正式审查报告，支持人工复核、编辑与定稿。"
    />
  ),
})
