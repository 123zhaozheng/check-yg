import { QueryClient } from "@tanstack/react-query"

/** Shared TanStack Query client — cookie auth, conservative stale time. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})
