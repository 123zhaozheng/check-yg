import { createFileRoute } from "@tanstack/react-router"
import { TabPlaceholder } from "@/components/layout/tab-placeholder"

/** AI 分析 /tasks/:id/analyze (docs §C4). Placeholder — S6 wires LLM review + anomalies. */
export const Route = createFileRoute("/__authenticated/tasks/$id/analyze")({
  component: () => (
    <TabPlaceholder
      title="AI 分析"
      description="对标准化流水运行 AI 审查模型，发现异常与风险点并展示。"
    />
  ),
})
