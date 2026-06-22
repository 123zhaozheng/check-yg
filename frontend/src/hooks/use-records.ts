import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  commitCleaning,
  exportCleaningLog,
  listExcluded,
  listTaskRecords,
  restoreRecord,
  type RecordListParams,
  type RecordType,
} from "@/lib/api"

/**
 * Cleaning / Standardization query keys (S5).
 *
 * `RECORDS_QUERY_KEY` namespaces the standard-records list + the excluded list
 * (both read from the same flow_records table). `invalidateQueries` on this
 * prefix refetches every variant after a restore / commit mutation.
 */
export const RECORDS_QUERY_KEY = ["records"] as const

/** Read the standard (cleaned) records for a task, paginated. */
export function useTaskRecords(taskId: number, params: RecordListParams = {}) {
  return useQuery({
    queryKey: [...RECORDS_QUERY_KEY, "list", taskId, params],
    queryFn: () => listTaskRecords(taskId, params),
    placeholderData: (prev) => prev,
  })
}

/** Read excluded + unparsed rows (active only) — the 可捞回 view.
 * `record_type` narrows to one type so the 非流水表 / 噪音行 sub-tabs paginate
 * independently (a mixed page filtered client-side would show empty slots when
 * one type is sparse on a page). */
export function useExcludedRecords(
  taskId: number,
  params: { page?: number; page_size?: number; record_type?: RecordType } = {},
) {
  return useQuery({
    queryKey: [...RECORDS_QUERY_KEY, "excluded", taskId, params],
    queryFn: () => listExcluded(taskId, params),
    placeholderData: (prev) => prev,
  })
}

/** Restore an excluded/unparsed row (mark status=restored, row stays). */
export function useRestoreRecord(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (recordId: number) => restoreRecord(taskId, recordId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: RECORDS_QUERY_KEY })
    },
  })
}

/** Commit the cleaning snapshot (lock standard records for downstream). */
export function useCommitCleaning(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => commitCleaning(taskId),
    onSuccess: () => {
      // The task itself changes (config.cleaning_committed), so refetch tasks.
      void queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })
}

/**
 * Export the cleaning log (unparsed/excluded with raw_payload + reason).
 * Triggers a browser download from the streamed CSV/JSON response.
 */
export function useExportCleaningLog(taskId: number) {
  return useMutation({
    mutationFn: async (format: "csv" | "json") => {
      const response = await exportCleaningLog(taskId, format)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      // Derive a filename from the content-disposition header if present,
      // otherwise fall back to a sensible default.
      const disposition = response.headers.get("content-disposition") || ""
      const match = disposition.match(/filename="?([^";]+)"?/i)
      a.download = match ? match[1] : `cleaning_log_${taskId}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    },
  })
}
