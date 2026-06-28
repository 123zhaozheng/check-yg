import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  chatAnalyze,
  createConversation,
  deleteConversation,
  getConversationHistory,
  listConversations,
  listFindings,
  patchFinding,
  startAnalysis,
  type FindingListParams,
  type PatchFindingRequest,
} from "@/lib/api"
import {
  type AnalysisProgressResource,
  openAnalysisProgressSocket,
} from "@/lib/websocket"

/**
 * AI Analysis query keys (S6 + 06-26-ai-agent).
 *
 * `FINDINGS_QUERY_KEY` namespaces the findings list. `invalidateQueries` on
 * this prefix refetches every variant after an analyze / patch mutation.
 * `CONVERSATIONS_QUERY_KEY` namespaces the per-task 追问会话 list (悬浮球扇形展开).
 */
export const FINDINGS_QUERY_KEY = ["findings"] as const
export const CONVERSATIONS_QUERY_KEY = ["conversations"] as const

/** Read findings for a task, severity + status filter (severity-desc sorted). */
export function useFindings(taskId: number, params: FindingListParams = {}) {
  return useQuery({
    queryKey: [...FINDINGS_QUERY_KEY, "list", taskId, params],
    queryFn: () => listFindings(taskId, params),
    placeholderData: (prev) => prev,
  })
}

/**
 * Read findings with a short refetch interval — polling **fallback** for when
 * the WebSocket `analysis.progress` channel is not connected. RVP (06-26-ai-agent):
 * WS is primary (cookie auth now reaches `/ws`), this query is the safety net so
 * newly-landed 维度 findings still increment into the left list if WS drops.
 * Pass `enabled = running && !wsHealthy` so the two paths don't both run and
 * duplicate work; WS断时轮询接手.
 */
export function useFindingsLive(taskId: number, enabled: boolean) {
  return useQuery({
    queryKey: [...FINDINGS_QUERY_KEY, "list", taskId, {}],
    queryFn: () => listFindings(taskId, {}),
    placeholderData: (prev) => prev,
    refetchInterval: enabled ? 1500 : false,
  })
}

/**
 * Subscribe to the WebSocket `analysis.progress` event for one task while
 * `active` is true. Returns the latest progress resource + a `healthy` flag.
 *
 * RVP (06-26-ai-agent): WS is the primary real-time channel now that the
 * backend authenticates `/ws` via the `access_token` httpOnly cookie (browser
 * attaches it on the handshake — no JS-readable token needed). The caller
 * uses `healthy` to gate the `useFindingsLive` polling fallback so WS and
 * polling never both run wide-open (avoiding duplicate increments).
 *
 * Closes the socket on unmount / task switch / `active` going false.
 */
export function useAnalysisProgress(
  taskId: number,
  active: boolean,
  onProgress?: (res: AnalysisProgressResource) => void,
): { progress: AnalysisProgressResource | null; healthy: boolean } {
  const [progress, setProgress] = useState<AnalysisProgressResource | null>(null)
  const [healthy, setHealthy] = useState(false)
  const onProgressRef = useRef(onProgress)
  onProgressRef.current = onProgress

  useEffect(() => {
    if (!active) {
      setProgress(null)
      setHealthy(false)
      return
    }
    const ctrl = openAnalysisProgressSocket(taskId, (res) => {
      setProgress(res)
      onProgressRef.current?.(res)
    })
    // Poll the controller's healthy flag a couple times to surface the open
    // state (WS onopen fires async). Lightweight; the fallback poller reads
    // this via the return value refreshed on each render.
    const pollHandle = setInterval(() => {
      setHealthy(ctrl.healthy())
    }, 500)
    return () => {
      clearInterval(pollHandle)
      ctrl.close()
    }
  }, [taskId, active])

  return { progress, healthy }
}

/**
 * Trigger AI analysis (异步 background task；立即返 started + 维度数).
 * 成功后 invalidate findings + task（拉最新 last_analysis_at / last_analysis_summary）.
 */
export function useStartAnalysis(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => startAnalysis(taskId, {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: FINDINGS_QUERY_KEY })
      // task.config.last_analysis_at / last_analysis_summary changed → refetch task.
      void queryClient.invalidateQueries({ queryKey: ["tasks"] })
    },
  })
}

/** Patch a finding's status / comment. */
export function usePatchFinding(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      findingId,
      body,
    }: {
      findingId: number
      body: PatchFindingRequest
    }) => patchFinding(findingId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...FINDINGS_QUERY_KEY, "list", taskId],
      })
    },
  })
}

/**
 * Multi-turn chat with the AI 追问 agent (悬浮球面板).
 *
 * Passes `conversation_id` so the backend appends to the right AuditConversation
 * (首轮流建会话). The backend persists real `message_history`; the frontend keeps
 * its own echo of the current conversation for display (多会话历史在后端，前端
 * 只存当前展示的 echo).
 */
export function useChatAnalyze(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      message,
      conversationId,
    }: {
      message: string
      conversationId?: number | null
    }) => chatAnalyze(taskId, message, conversationId),
    onSuccess: () => {
      // 新会话首轮流会建会话 → 刷新会话列表（悬浮球扇形展开项）.
      void queryClient.invalidateQueries({
        queryKey: [...CONVERSATIONS_QUERY_KEY, "list", taskId],
      })
    },
  })
}

/** GET /api/tasks/{taskId}/analyze/conversations — 会话列表（悬浮球扇形展开）. */
export function useConversations(taskId: number) {
  return useQuery({
    queryKey: [...CONVERSATIONS_QUERY_KEY, "list", taskId],
    queryFn: () => listConversations(taskId),
    staleTime: 10 * 1000,
  })
}

/** GET /api/tasks/{taskId}/analyze/conversations/{id} — 取会话历史（点历史会话回放）.
 *  ``conversationId`` 为 null 时禁用（新建会话，无历史可拉）。关掉 window-focus
 *  重取：历史只 seed 进本地 messages 一次，避免重取覆盖用户在本轮新发的 echo. */
export function useConversationHistory(
  taskId: number,
  conversationId: number | null,
) {
  return useQuery({
    queryKey: [...CONVERSATIONS_QUERY_KEY, "detail", taskId, conversationId],
    queryFn: () => getConversationHistory(taskId, conversationId as number),
    enabled: conversationId != null,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  })
}

/** POST /api/tasks/{taskId}/analyze/conversations — 新建会话（点 ＋ 新建）. */
export function useCreateConversation(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (title?: string) => createConversation(taskId, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...CONVERSATIONS_QUERY_KEY, "list", taskId],
      })
    },
  })
}

/** DELETE /api/tasks/{taskId}/analyze/conversations/{id} — 删会话. */
export function useDeleteConversation(taskId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (conversationId: number) =>
      deleteConversation(taskId, conversationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: [...CONVERSATIONS_QUERY_KEY, "list", taskId],
      })
    },
  })
}
