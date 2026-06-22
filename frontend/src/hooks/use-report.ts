import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  createAnnotation,
  finalizeReport,
  generateReport,
  getReport,
  patchChapter,
  regenerateChapter,
  regenerateReport,
  reorderChapters,
  toggleAnnotation,
  type ReportAnnotationCreateBody,
  type ReportChapterPatchBody,
  type ReportChapterReorderItem,
} from "@/lib/api"

/**
 * S7 审查报告闭环 query keys.
 *
 * `REPORT_QUERY_KEY` namespaces the per-task report detail (chapters +
 * annotations). `invalidateQueries` on this prefix refetches every task's
 * report after a generate / patch / regenerate / reorder / annotation /
 * finalize mutation.
 */
export const REPORT_QUERY_KEY = ["reports"] as const

/** Read the current report for a task (chapters + annotations). */
export function useReport(taskId: number) {
  return useQuery({
    queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
    queryFn: () => getReport(taskId),
    // generate / regenerate rewrite chapters; keep stale time conservative.
    placeholderData: (prev) => prev,
    retry: false,
  })
}

/** POST /tasks/{taskId}/report — 章节化生成（幂等：已有则返已有）. */
export function useGenerateReport(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => generateReport(taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}

/** PATCH /reports/{id}/chapters/{cid} — 行内编辑章节 content（定稿 409）. */
export function usePatchChapter(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      reportId,
      chapterId,
      body,
    }: {
      reportId: number
      chapterId: number
      body: ReportChapterPatchBody
    }) => patchChapter(reportId, chapterId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}

/** POST /reports/{id}/chapters/{cid}/regenerate — 单章重生成（定稿 409）. */
export function useRegenerateChapter(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      reportId,
      chapterId,
    }: {
      reportId: number
      chapterId: number
    }) => regenerateChapter(reportId, chapterId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}

/** POST /reports/{id}/chapters/reorder — 拖拽排序（定稿 409）. */
export function useReorderChapters(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      reportId,
      items,
    }: {
      reportId: number
      items: ReportChapterReorderItem[]
    }) => reorderChapters(reportId, items),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}

/** POST /reports/{id}/regenerate — 全报告重生成（定稿 409）. */
export function useRegenerateReport(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (reportId: number) => regenerateReport(reportId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}

/** POST /reports/{id}/annotations — 新建批注（定稿 409）. */
export function useAddAnnotation(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      reportId,
      body,
    }: {
      reportId: number
      body: ReportAnnotationCreateBody
    }) => createAnnotation(reportId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}

/** PATCH /reports/{id}/annotations/{aid} — 切 resolved（定稿 409）. */
export function usePatchAnnotation(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      reportId,
      annotationId,
    }: {
      reportId: number
      annotationId: number
    }) => toggleAnnotation(reportId, annotationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}

/** POST /reports/{id}/finalize — 定稿 status→final. */
export function useFinalizeReport(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (reportId: number) => finalizeReport(reportId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...REPORT_QUERY_KEY, "detail", taskId],
      })
    },
  })
}
