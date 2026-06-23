import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  archiveTask,
  createTask,
  getTask,
  listTasks,
  startExtraction,
  type TaskCreatePayload,
  type TaskListParams,
} from "@/lib/api"
import { DOCUMENTS_QUERY_KEY } from "@/hooks/use-documents"

/**
 * Task list query key — namespace + the filter params object. `invalidateQueries`
 * on this prefix refetches every variant after a create/archive mutation.
 */
export const TASKS_QUERY_KEY = ["tasks"] as const

/**
 * Read the task list with filters. `params` is held in the query key so each
 * filter combination caches independently.
 */
export function useTaskList(params: TaskListParams) {
  return useQuery({
    queryKey: [...TASKS_QUERY_KEY, params],
    queryFn: () => listTasks(params),
    placeholderData: (prev) => prev,
  })
}

/** Read a single task by id (for config-derived fields like last_analysis_at). */
export function useTask(taskId: number) {
  return useQuery({
    queryKey: [...TASKS_QUERY_KEY, "detail", taskId],
    queryFn: () => getTask(taskId),
    placeholderData: (prev) => prev,
  })
}

/** Create a task then invalidate the task list so the new row shows up. */
export function useCreateTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: TaskCreatePayload) => createTask(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TASKS_QUERY_KEY })
    },
  })
}

/** Archive a task then invalidate the list so it drops out of the default view. */
export function useArchiveTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (taskId: number) => archiveTask(taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TASKS_QUERY_KEY })
    },
  })
}

/**
 * Manually start extraction for a task (uploads no longer auto-start). On
 * success invalidate both the task detail (so status flips to running) and the
 * documents list (so polling resumes and parse status updates in real time).
 */
export function useStartExtraction(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => startExtraction(taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TASKS_QUERY_KEY })
      void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY })
    },
  })
}
