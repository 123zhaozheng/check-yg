import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { AppShell } from "@/components/layout/app-shell"
import { fetchCurrentUser } from "@/hooks/use-current-user"

/**
 * Authenticated layout (docs §A2). Wraps every page behind the app shell.
 *
 * `beforeLoad` is the real auth guard: it prefills the current user via the
 * shared QueryClient (so the `useCurrentUser` hook in the shell and pages hits
 * the cache). `apiFetch` already does a silent `/auth/refresh` + replay on a
 * stale access cookie, so reaching the `catch` means refresh also failed — we
 * bounce to /login with a `redirect` back to the attempted path.
 */
export const Route = createFileRoute("/__authenticated")({
  beforeLoad: async ({ context, location }) => {
    if (!context.queryClient) {
      throw redirect({ to: "/login", search: { redirect: location.href } })
    }
    try {
      const user = await fetchCurrentUser(context.queryClient)
      return { user }
    } catch {
      throw redirect({
        to: "/login",
        search: { redirect: location.href },
      })
    }
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
})
