import { createFileRoute, redirect } from "@tanstack/react-router"

/** /tasks/:id → redirect to the overview tab. */
export const Route = createFileRoute("/__authenticated/tasks/$id/")({
  beforeLoad: ({ params }) => {
    throw redirect({ to: "/tasks/$id/overview", params: { id: params.id } })
  },
  component: () => null,
})
