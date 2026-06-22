import { useQuery, useQueryClient } from "@tanstack/react-query"

import { getDashboard, type DashboardData } from "@/lib/api"

/**
 * Dashboard aggregation (docs §B1 / S2).
 *
 * Backed by TanStack Query so the result is cached and shared. REFRESH on the
 * page calls `invalidateDashboard()` to refetch.
 */
export const DASHBOARD_QUERY_KEY = ["dashboard"] as const

export function useDashboard() {
  const query = useQuery({
    queryKey: DASHBOARD_QUERY_KEY,
    queryFn: () => getDashboard(),
  })
  return {
    data: query.data,
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
