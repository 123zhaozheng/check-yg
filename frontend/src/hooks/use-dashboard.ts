import { useQuery, useQueryClient } from "@tanstack/react-query"

import { getDashboard, type DashboardData } from "@/lib/api"

/**
 * Dashboard aggregation (docs §B1 / S2).
 *
 * Backed by TanStack Query so the result is cached and shared. REFRESH on the
 * page calls `invalidateDashboard()` to refetch. `refetchInterval` (30s) gives
 * the landing page a passive refresh — "上次同步" in the header reflects the
 * actual `dataUpdatedAt` rather than a stale row timestamp.
 */
export const DASHBOARD_QUERY_KEY = ["dashboard"] as const

// Passive polling for the landing page; the explicit REFRESH button still
// refetches on demand via queryClient.invalidateQueries. 30s keeps the
// "上次同步: 刚刚" affordance honest without hammering the API.
const REFETCH_INTERVAL_MS = 30_000

export function useDashboard() {
  const query = useQuery({
    queryKey: DASHBOARD_QUERY_KEY,
    queryFn: () => getDashboard(),
    refetchInterval: REFETCH_INTERVAL_MS,
  })
  return {
    data: query.data,
    dataUpdatedAt: query.dataUpdatedAt,
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching: query.isFetching,
    query,
  }
}

/** Invalidate the dashboard query — used by the REFRESH button. */
export function useInvalidateDashboard() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: DASHBOARD_QUERY_KEY })
}

export type { DashboardData }
