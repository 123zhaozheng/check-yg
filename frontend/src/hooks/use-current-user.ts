import { useQuery } from "@tanstack/react-query"
import type { QueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

/**
 * Current user shape — mirrors `backend/app/schemas/auth.py::UserResponse`
 * returned by `GET /api/auth/me`.
 */
export interface CurrentUser {
  id: number
  username: string
  email: string
  role: string
  is_active: boolean
}

export const CURRENT_USER_QUERY_KEY = ["auth", "me"] as const

/**
 * React hook for the current user. Backed by TanStack Query so the result is
 * cached and shared with the router's `beforeLoad` prefill (see
 * `fetchCurrentUser`). `apiFetch` already handles silent refresh + replay on
 * 401, so a hard error here means refresh also failed (caller should bail).
 */
export function useCurrentUser() {
  const query = useQuery({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: () => api.get<CurrentUser>("/auth/me"),
    retry: false,
  })
  return {
    user: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    query,
  }
}

/**
 * Prefetch the current user for router `beforeLoad` guards. Resolves with the
 * user when already cached or freshly fetched; throws (ApiError 401) when the
 * access cookie is missing/expired AND the silent refresh also failed — the
 * caller catches that and `throw redirect({ to: "/login" })`.
 */
export async function fetchCurrentUser(
  queryClient: QueryClient,
): Promise<CurrentUser> {
  return queryClient.fetchQuery({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: () => api.get<CurrentUser>("/auth/me"),
    staleTime: 60 * 1000,
    // Auth 401s must not retry — apiFetch already does a silent refresh + one
    // replay; a second /auth/me would just re-hit 401 and waste a round-trip.
    retry: false,
  })
}
