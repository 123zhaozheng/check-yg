import { createFileRoute, Outlet } from "@tanstack/react-router"
import { AppShell } from "@/components/layout/app-shell"

/**
 * Authenticated layout (docs §A2). Wraps every page behind the app shell.
 *
 * Auth guard is a placeholder here — S1 (login slice) wires the real
 * /api/auth/me check via `beforeLoad`. Today it just renders the shell so
 * routes are walkable during infra verification.
 */
export const Route = createFileRoute("/__authenticated")({
  beforeLoad: () => {
    // Placeholder for S1: real cookie check goes here.
    // const me = await queryClient.ensureQueryData(...)
    // if (!me) throw redirect({ to: "/login" })
    return {}
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
})
