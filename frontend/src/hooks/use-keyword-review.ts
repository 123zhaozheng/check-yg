import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  listKeywordHits,
  patchKeywordHit,
  runKeywordReview,
  type KeywordHitPatchBody,
  type KeywordReviewRunBody,
} from "@/lib/api"

/**
 * 06-23-tab keyword review query keys (task-level).
 *
 * `KEYWORD_REVIEW_QUERY_KEY` namespaces a task's hits list. Mutations
 * (run/patch) invalidate the relevant cache so the UI reflects the new state.
 */
export const KEYWORD_REVIEW_QUERY_KEY = ["keyword-review"] as const

/** GET /api/tasks/{taskId}/keyword-review/hits — 分页列命中（支持过滤）. */
export function useKeywordHits(
  taskId: number,
  params: {
    status?: "pending" | "confirmed" | "ignored"
    risk_level?: "高" | "中" | "低"
    match_type?: "精确匹配" | "脱敏匹配" | "模糊匹配"
    page?: number
    page_size?: number
  } = {},
) {
  return useQuery({
    queryKey: [...KEYWORD_REVIEW_QUERY_KEY, "hits", taskId, params],
    queryFn: () => listKeywordHits(taskId, params),
    placeholderData: (prev) => prev,
  })
}

/** POST /api/tasks/{taskId}/keyword-review/run — 运行关键词审查（owner）. */
export function useRunKeywordReview(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: KeywordReviewRunBody) => runKeywordReview(taskId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...KEYWORD_REVIEW_QUERY_KEY, "hits", taskId],
      })
      void queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })
}

/** PATCH /api/tasks/{taskId}/keyword-review/hits/{hitId} — 改命中 status / note. */
export function usePatchKeywordHit(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ hitId, body }: { hitId: number; body: KeywordHitPatchBody }) =>
      patchKeywordHit(taskId, hitId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...KEYWORD_REVIEW_QUERY_KEY, "hits", taskId],
      })
    },
  })
}
