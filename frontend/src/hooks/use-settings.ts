import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  changePassword,
  getSettingsSchema,
  listSettings,
  updateMe,
  updateSetting,
  type ChangePasswordBody,
  type UpdateMeBody,
} from "@/lib/api"
import { CURRENT_USER_QUERY_KEY } from "@/hooks/use-current-user"

/**
 * S8 设置页 query keys.
 *
 * `SETTINGS_QUERY_KEY` namespaces the schema + saved-values lists. Mutations
 * (updateSetting / changePassword / updateMe) invalidate the relevant cache so
 * the form reflects the new value without a manual refetch.
 */
export const SETTINGS_QUERY_KEY = ["settings"] as const

/** GET /api/settings/schema — 设置项元数据列表（供前端表单渲染）. */
export function useSettingsSchema() {
  return useQuery({
    queryKey: [...SETTINGS_QUERY_KEY, "schema"],
    queryFn: () => getSettingsSchema(),
    staleTime: 60 * 1000,
  })
}

/** GET /api/settings/ — 所有设置项已存值. */
export function useSettings() {
  return useQuery({
    queryKey: [...SETTINGS_QUERY_KEY, "list"],
    queryFn: () => listSettings(),
    staleTime: 30 * 1000,
  })
}

/** PUT /api/settings/{key} — 更新单个设置项（落 Setting 表）. */
export function useUpdateSetting() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      updateSetting(key, value),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...SETTINGS_QUERY_KEY] })
    },
  })
}

/** POST /api/auth/change-password — 改密码（校验旧密码 + 新密码长度≥8）. */
export function useChangePassword() {
  return useMutation({
    mutationFn: (body: ChangePasswordBody) => changePassword(body),
  })
}

/**
 * PATCH /api/users/me — 当前用户改个人信息（username/email，非 admin-only）.
 *
 * Invalidates the current-user cache so the shell's avatar/name updates after
 * a rename.
 */
export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UpdateMeBody) => updateMe(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY })
      void queryClient.invalidateQueries({ queryKey: [...SETTINGS_QUERY_KEY] })
    },
  })
}
