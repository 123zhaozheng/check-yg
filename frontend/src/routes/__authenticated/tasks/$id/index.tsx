import { createFileRoute, redirect } from "@tanstack/react-router"

/** /tasks/:id → redirect to the 数据导入 tab (06-23-tab: 概览已删，落到导入). */
export const Route = createFileRoute("/__authenticated/tasks/$id/")({
  beforeLoad: ({ params }) => {
    throw redirect({ to: "/tasks/$id/import", params: { id: params.id } })
  },
  component: () => null,
})
