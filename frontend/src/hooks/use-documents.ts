import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  deleteDocument,
  listDocuments,
  uploadTaskDocuments,
  type DocumentListParams,
} from "@/lib/api"

/**
 * Document list query key — namespaced by task id + params. `invalidateQueries`
 * on this prefix refetches every variant after an upload / delete mutation.
 */
export const DOCUMENTS_QUERY_KEY = ["documents"] as const

/**
 * Read the document list for a task. `refetchInterval` is dynamic: poll every
 * 2s while any document is pending/processing, stop once all are
 * completed/failed/deleted — so the UI updates parse status in real time
 * without hammering the API after the work is done.
 */
export function useDocumentList(taskId: number, params: DocumentListParams = {}) {
  return useQuery({
    queryKey: [...DOCUMENTS_QUERY_KEY, taskId, params],
    queryFn: () => listDocuments(taskId, params),
    placeholderData: (prev) => prev,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      const active = data.items.some(
        (d) => d.status === "pending" || d.status === "processing",
      )
      return active ? 2000 : false
    },
  })
}

/**
 * Upload files to an existing task with a channel label. On success invalidate
 * the documents list so the new pending rows show up immediately.
 */
export function useUploadTaskDocuments(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ files, channel }: { files: File[]; channel?: string }) =>
      uploadTaskDocuments(taskId, files, channel),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY })
    },
  })
}

/** Soft-delete a document; invalidate the list so it drops out of the default view. */
export function useDeleteDocument(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (docId: number) => deleteDocument(taskId, docId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY })
    },
  })
}
