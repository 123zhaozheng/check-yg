import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  createKeywordCard,
  deleteKeywordCard,
  exportKeywordLibrary,
  getKeywordCard,
  importKeywordLibrary,
  listKeywordCards,
  updateKeywordCard,
  type KeywordCardUpsertBody,
} from "@/lib/api"

/**
 * 06-23-tab keyword library query keys.
 *
 * `KEYWORD_LIBRARY_QUERY_KEY` namespaces the cards list + card detail. Mutations
 * invalidate the relevant cache so the UI reflects the new state without a
 * manual refetch.
 */
export const KEYWORD_LIBRARY_QUERY_KEY = ["keyword-library"] as const

/** GET /api/keyword-library/cards — 卡片列表（含 term 数 + 风险等级）. */
export function useKeywordCards() {
  return useQuery({
    queryKey: [...KEYWORD_LIBRARY_QUERY_KEY, "cards"],
    queryFn: () => listKeywordCards(),
    staleTime: 30 * 1000,
  })
}

/** GET /api/keyword-library/cards/{id} — 卡片详情（含 terms 列表）. */
export function useKeywordCard(cardId: number | null) {
  return useQuery({
    queryKey: [...KEYWORD_LIBRARY_QUERY_KEY, "card", cardId],
    queryFn: () => getKeywordCard(cardId as number),
    enabled: cardId !== null,
    staleTime: 30 * 1000,
  })
}

/** POST /api/keyword-library/cards — 新建卡片（admin）. */
export function useCreateKeywordCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: KeywordCardUpsertBody) => createKeywordCard(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...KEYWORD_LIBRARY_QUERY_KEY] })
    },
  })
}

/** PUT /api/keyword-library/cards/{id} — 编辑卡片（admin；terms 全量替换）. */
export function useUpdateKeywordCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: KeywordCardUpsertBody }) =>
      updateKeywordCard(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...KEYWORD_LIBRARY_QUERY_KEY] })
    },
  })
}

/** DELETE /api/keyword-library/cards/{id} — 删卡（admin；被引用返 409）. */
export function useDeleteKeywordCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteKeywordCard(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...KEYWORD_LIBRARY_QUERY_KEY] })
    },
  })
}

/** POST /api/keyword-library/import — excel 导入（admin，multipart）. */
export function useImportKeywordLibrary() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => importKeywordLibrary(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...KEYWORD_LIBRARY_QUERY_KEY] })
    },
  })
}

/**
 * GET /api/keyword-library/export — excel 导出（触发浏览器下载）.
 * 所有登录用户可读（非 admin-only）。
 */
export function useExportKeywordLibrary() {
  return useMutation({
    mutationFn: async () => {
      const response = await exportKeywordLibrary()
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      const disposition = response.headers.get("content-disposition") || ""
      const match = disposition.match(/filename="?([^";]+)"?/i)
      a.download = match ? match[1] : "keyword_library.xlsx"
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    },
  })
}
