import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  createLLMModel,
  deleteLLMModel,
  listLLMModels,
  listLLMModelAssignments,
  updateLLMModel,
  upsertLLMModelAssignment,
  type LLMModelAssignmentBody,
  type LLMModelUpsertBody,
  type Stage,
} from "@/lib/api"

/**
 * 06-23-llm-model-card query keys.
 *
 * `LLM_MODELS_QUERY_KEY` namespaces the model-cards list + the stage-assignments
 * list. Mutations invalidate the relevant cache so the UI reflects the new state
 * without a manual refetch.
 */
export const LLM_MODELS_QUERY_KEY = ["llm-models"] as const

/** GET /api/llm-models — 模型卡片列表（api_key 脱敏）. */
export function useLLMModels() {
  return useQuery({
    queryKey: [...LLM_MODELS_QUERY_KEY, "list"],
    queryFn: () => listLLMModels(),
    staleTime: 30 * 1000,
  })
}

/** GET /api/llm-model-assignments — 6 阶段指派列表. */
export function useLLMModelAssignments() {
  return useQuery({
    queryKey: [...LLM_MODELS_QUERY_KEY, "assignments"],
    queryFn: () => listLLMModelAssignments(),
    staleTime: 30 * 1000,
  })
}

/** POST /api/llm-models — 新建模型卡片（admin）. */
export function useCreateLLMModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LLMModelUpsertBody) => createLLMModel(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...LLM_MODELS_QUERY_KEY] })
    },
  })
}

/** PUT /api/llm-models/{id} — 更新模型卡片（admin；api_key 留空不改）. */
export function useUpdateLLMModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: LLMModelUpsertBody }) =>
      updateLLMModel(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...LLM_MODELS_QUERY_KEY] })
    },
  })
}

/** DELETE /api/llm-models/{id} — 删除模型卡片（admin；被指派返 409）. */
export function useDeleteLLMModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteLLMModel(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...LLM_MODELS_QUERY_KEY] })
    },
  })
}

/** PUT /api/llm-model-assignments/{stage} — 指派/解除阶段卡片（admin）. */
export function useUpsertLLMModelAssignment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ stage, body }: { stage: Stage; body: LLMModelAssignmentBody }) =>
      upsertLLMModelAssignment(stage, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...LLM_MODELS_QUERY_KEY] })
    },
  })
}
