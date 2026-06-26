import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  createAuditDimension,
  deleteAuditDimension,
  getAuditDimension,
  listAuditDimensions,
  updateAuditDimension,
  type AuditDimensionCreateBody,
  type AuditDimensionUpdateBody,
} from "@/lib/api"

/**
 * 06-26-ai-agent 审查维度 query keys.
 *
 * `AUDIT_DIMENSIONS_QUERY_KEY` namespaces the dimension list. Mutations
 * invalidate the cache so the 管理页 + analyze 跑分析读到的维度集都是最新.
 */
export const AUDIT_DIMENSIONS_QUERY_KEY = ["audit-dimensions"] as const

/** GET /api/audit-dimensions — 维度列表（所有登录用户可读）. */
export function useAuditDimensions() {
  return useQuery({
    queryKey: [...AUDIT_DIMENSIONS_QUERY_KEY, "list"],
    queryFn: () => listAuditDimensions(),
    staleTime: 30 * 1000,
  })
}

/** GET /api/audit-dimensions/{id} — 维度详情（含 steps / judgment / prompt）.
 *  编辑弹窗用此拉 judgment（列表项不含 judgment）. */
export function useAuditDimension(id: number | null) {
  return useQuery({
    queryKey: [...AUDIT_DIMENSIONS_QUERY_KEY, "detail", id],
    queryFn: () => getAuditDimension(id as number),
    enabled: id !== null,
    staleTime: 30 * 1000,
  })
}

/** POST /api/audit-dimensions — 新建维度（admin）. */
export function useCreateAuditDimension() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AuditDimensionCreateBody) => createAuditDimension(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...AUDIT_DIMENSIONS_QUERY_KEY] })
    },
  })
}

/** PUT /api/audit-dimensions/{id} — 编辑维度（admin；任一字段变化后端重拼 prompt）. */
export function useUpdateAuditDimension() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: AuditDimensionUpdateBody }) =>
      updateAuditDimension(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...AUDIT_DIMENSIONS_QUERY_KEY] })
    },
  })
}

/** DELETE /api/audit-dimensions/{id} — 删维度（admin；被 finding 引用返 409）. */
export function useDeleteAuditDimension() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteAuditDimension(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...AUDIT_DIMENSIONS_QUERY_KEY] })
    },
  })
}
