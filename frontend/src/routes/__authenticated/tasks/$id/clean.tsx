import { createFileRoute } from "@tanstack/react-router"
import { TabPlaceholder } from "@/components/layout/tab-placeholder"

/** 清洗标准化 /tasks/:id/clean (docs §C3). Placeholder — S5 wires rules + diff view. */
export const Route = createFileRoute("/__authenticated/tasks/$id/clean")({
  component: () => (
    <TabPlaceholder
      title="清洗标准化"
      description="多渠道异构流水清洗为统一标准 schema，展示规则命中与清洗前后对照。"
    />
  ),
})
