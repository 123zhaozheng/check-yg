import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  chatAnalyze,
  listFindings,
  patchFinding,
  startAnalysis,
  type FindingListParams,
  type PatchFindingRequest,
} from "@/lib/api"

/**
 * AI Analysis query keys (S6).
 *
 * `FINDINGS_QUERY_KEY` namespaces the findings list. `invalidateQueries` on
 * this prefix refetches every variant after an analyze / patch mutation.
 */
export const FINDINGS_QUERY_KEY = ["findings"] as const

/** Read findings for a task, severity + status filter (severity-desc sorted). */
export function useFindings(taskId: number, params: FindingListParams = {}) {
  return useQuery({
    queryKey: [...FINDINGS_QUERY_KEY, "list", taskId, params],
    queryFn: () => listFindings(taskId, params),
    placeholderData: (prev) => prev,
  })
}

/** Trigger AI analysis (placeholder建 finding + 写 last_analysis_at). */
export function useStartAnalysis(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (mode: "quick" | "deep" = "quick") =>
      startAnalysis(taskId, { mode }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: FINDINGS_QUERY_KEY })
      // task.config.last_analysis_at changed → refetch task.
      void queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })
}

/** Patch a finding's status / comment. */
export function usePatchFinding(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      findingId,
      body,
    }: {
      findingId: number
      body: PatchFindingRequest
    }) => patchFinding(findingId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...FINDINGS_QUERY_KEY, "list", taskId],
      })
    },
  })
}

/**
 * Multi-turn chat with the AI analysis agent.
 *
 * Maintains a local optimistic message list (user bubble + AI placeholder
 * bubble appended on success). The backend persists the real
 * `analysis_chat_history` to `Task.config`; the frontend keeps its own echo
 * of the conversation for display. No query invalidation needed — chat
 * history isn't read back via the findings query.
 */
export function useChatAnalyze(taskId: number) {
  return useMutation({
    mutationFn: (message: string) => chatAnalyze(taskId, message),
  })
}
