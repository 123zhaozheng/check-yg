import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  downloadExport,
  exportTaskData,
  exportTaskReport,
  listTaskExports,
  previewTaskExport,
  type DataExportBody,
  type ExportScope,
  type ReportExportBody,
} from "@/lib/api"

/**
 * S8 导出闭环 query keys.
 *
 * `EXPORTS_QUERY_KEY` namespaces the per-task export history list.
 * `PREVIEW_QUERY_KEY` namespaces the per-task + scope preview sample.
 * Mutations invalidate the history list so a freshly generated export
 * shows up in the table without a manual refetch.
 */
export const EXPORTS_QUERY_KEY = ["exports"] as const

/** GET /tasks/{taskId}/exports — 导出历史列表（按 created_at 降序）. */
export function useExportHistory(taskId: number) {
  return useQuery({
    queryKey: [...EXPORTS_QUERY_KEY, "history", taskId],
    queryFn: () => listTaskExports(taskId),
    placeholderData: (prev) => prev,
  })
}

/** GET /tasks/{taskId}/export/preview?scope=... — 取样预览（不生成产物）. */
export function useExportPreview(taskId: number, scope: ExportScope) {
  return useQuery({
    queryKey: [...EXPORTS_QUERY_KEY, "preview", taskId, scope],
    queryFn: () => previewTaskExport(taskId, scope),
    enabled: !!taskId,
  })
}

/** POST /tasks/{taskId}/export/report — 报告多格式导出（pdf/docx/html）. */
export function useExportReport(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ReportExportBody) => exportTaskReport(taskId, body),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({
        queryKey: [...EXPORTS_QUERY_KEY, "history", taskId],
      })
      // 自动触发浏览器下载刚生成的产物（修复：点导出无下载，需去历史重新下载）
      void triggerExportDownload(data.id).catch(() => {
        // 下载失败不破坏导出成功状态；产物已入库，可在历史里重新下载
      })
    },
  })
}

/** POST /tasks/{taskId}/export/data — 数据多范围导出（raw/standard/findings × excel/csv）. */
export function useExportData(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: DataExportBody) => exportTaskData(taskId, body),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({
        queryKey: [...EXPORTS_QUERY_KEY, "history", taskId],
      })
      void triggerExportDownload(data.id).catch(() => {})
    },
  })
}

/**
 * Trigger a browser download for an existing export artifact.
 *
 * The backend streams the file via `GET /api/exports/{id}/download`; this helper
 * reads the response blob and re-creates it as an object URL so a normal
 * `<a download>` click works in the SPA. Not a React Query mutation (no cache
 * to invalidate) — just an async helper the page calls on click.
 */
export async function triggerExportDownload(exportId: number): Promise<void> {
  const response = await downloadExport(exportId)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  // Derive a filename from the Content-Disposition header if present, else fallback.
  const disposition = response.headers.get("Content-Disposition") || ""
  const match = /filename="?([^";]+)"?/.exec(disposition)
  a.download = match ? match[1] : `export_${exportId}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
