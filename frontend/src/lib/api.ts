/**
 * API client — cookie-based auth (httpOnly JWT access+refresh set by backend B1).
 *
 * All requests go through the Vite dev proxy (`/api` → http://localhost:8000)
 * so the browser sends the SameSite=Strict cookies automatically. In production
 * the FastAPI app serves the built SPA from the same origin, so the path is
 * identical and cookies flow without CORS plumbing.
 *
 * `credentials: "include"` is mandatory for the browser to attach cookies on
 * cross-origin dev (vite:5173 → api:8000 via proxy, same effective origin).
 *
 * 401 handling: instead of bouncing straight to /login, the client first tries
 * a silent `POST /api/auth/refresh` (cookie-driven) and replays the original
 * request once. Concurrent 401s share a single in-flight refresh promise so we
 * don't fan out N refreshes. The login and refresh endpoints themselves never
 * trigger a refresh-retry — their 401 propagates as an error (caller decides).
 */

const API_BASE = "/api"

/** Endpoints that must NOT trigger a silent refresh-retry on 401. */
const NO_REFRESH_ENDPOINTS = ["/auth/login", "/auth/refresh"]

function isNoRefreshEndpoint(endpoint: string): boolean {
  return NO_REFRESH_ENDPOINTS.some((p) => endpoint === p || endpoint.startsWith(`${p}/`))
}

export class ApiError extends Error {
  status: number
  statusText: string
  data?: unknown
  constructor(status: number, statusText: string, data?: unknown) {
    super(`API Error: ${status} ${statusText}`)
    this.name = "ApiError"
    this.status = status
    this.statusText = statusText
    this.data = data
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  params?: Record<string, string | number | boolean | undefined>
  /** JSON-serializable body, or FormData (sent as multipart). */
  body?: unknown
}

function buildUrl(
  endpoint: string,
  params?: ApiRequestOptions["params"],
): string {
  const url = `${API_BASE}${endpoint}`
  if (!params) return url
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    search.append(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${url}?${qs}` : url
}

/** Extract a human-readable detail string from a FastAPI error body. */
function extractErrorDetail(data: unknown): string | undefined {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === "string" && detail.length > 0) return detail
  }
  return undefined
}

/** Redirect to /login with a redirect back to the current path. SSR-safe. */
function redirectToLogin(): void {
  if (typeof window === "undefined") return
  const current = window.location.pathname + window.location.search
  if (current.startsWith("/login")) return
  window.location.replace(`/login?redirect=${encodeURIComponent(current)}`)
}

let refreshPromise: Promise<boolean> | null = null

/**
 * Trigger one silent token refresh. Concurrent callers share the same promise
 * (dedup) so N simultaneous 401s produce a single `/auth/refresh` round-trip.
 * Resolves true on success, false on any failure.
 */
function silentRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
        credentials: "include",
      })
      return res.ok
    } catch {
      return false
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

/**
 * Core fetch wrapper. Sends cookies, handles JSON, throws ApiError on non-2xx.
 * On 401 (excluding /auth/login & /auth/refresh) it silently refreshes once and
 * replays the original request; a second 401 or a failed refresh redirects to
 * /login with a `?redirect=` back to the current path.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { params, body, headers, ...rest } = options

  const isFormData = body instanceof FormData
  const finalHeaders: Record<string, string> = {
    ...(headers as Record<string, string>),
  }
  if (body !== undefined && !isFormData) {
    finalHeaders["Content-Type"] = "application/json"
  }

  const doFetch = (): Promise<Response> =>
    fetch(buildUrl(endpoint, params), {
      ...rest,
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
      headers: finalHeaders,
      credentials: "include",
    })

  let response = await doFetch()

  if (response.status === 401 && !isNoRefreshEndpoint(endpoint)) {
    const refreshed = await silentRefresh()
    if (refreshed) {
      // Replay the original request exactly once with the fresh access cookie.
      response = await doFetch()
    }
    if (response.status === 401) {
      redirectToLogin()
      let data: unknown
      try {
        data = await response.json()
      } catch {
        // non-JSON error body
      }
      throw new ApiError(401, "Unauthorized", data)
    }
  } else if (response.status === 401) {
    // /auth/login or /auth/refresh themselves returned 401 — surface the error,
    // don't bounce. Login page reads ApiError.data.detail for the message.
    let data: unknown
    try {
      data = await response.json()
    } catch {
      // non-JSON error body
    }
    throw new ApiError(401, "Unauthorized", data)
  }

  if (!response.ok) {
    let data: unknown
    try {
      data = await response.json()
    } catch {
      // non-JSON error body
    }
    throw new ApiError(response.status, response.statusText, data)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get("Content-Type") || ""
  if (contentType.includes("application/json")) {
    return (await response.json()) as T
  }
  // Non-JSON success (e.g. file downloads) — return raw response for caller.
  return response as unknown as T
}

/** Convenience verbs. */
export const api = {
  get: <T>(endpoint: string, params?: ApiRequestOptions["params"]) =>
    apiFetch<T>(endpoint, { method: "GET", params }),
  post: <T>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
    apiFetch<T>(endpoint, { method: "POST", body, ...options }),
  put: <T>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
    apiFetch<T>(endpoint, { method: "PUT", body, ...options }),
  patch: <T>(endpoint: string, body?: unknown, options?: ApiRequestOptions) =>
    apiFetch<T>(endpoint, { method: "PATCH", body, ...options }),
  delete: <T>(endpoint: string) => apiFetch<T>(endpoint, { method: "DELETE" }),
}

export { extractErrorDetail }

/* =========================================================================
 * Task API — types + helpers (S3 task list + new-task dialog).
 * Appended only; the apiFetch core above is unchanged.
 * ======================================================================= */

/** Mirrors `backend/app/routers/tasks.py::TaskResponse`. */
export interface TaskItem {
  id: number
  title: string
  description?: string | null
  status: string
  owner_id: number
  config?: Record<string, unknown> | null
  created_at: string
  updated_at: string
  completed_at?: string | null
  employee_name?: string | null
  employee_id?: string | null
  department?: string | null
  audit_start?: string | null
  audit_end?: string | null
  expected_channels?: string[] | null
  archived: boolean
  /** 后端推导的当前阶段中文 label（analyzing 细分 清洗完成/分析中/报告生成/已完成）。 */
  stage: string
}

export interface TaskListResponse {
  items: TaskItem[]
  total: number
  page: number
  page_size: number
}

/** Query params for GET /api/tasks (all optional, mirrors backend filters). */
export interface TaskListParams {
  page?: number
  page_size?: number
  status_filter?: string
  stage?: string
  created_after?: string
  created_before?: string
  employee_id?: string
  archived?: boolean
  search?: string
}

/** Payload for POST /api/tasks (new-task dialog). Only `title` is required. */
export interface TaskCreatePayload {
  title: string
  description?: string
  document_folder?: string
  batch_size?: number
  confidence_threshold?: number
  employee_name?: string
  employee_id?: string
  department?: string
  audit_start?: string
  audit_end?: string
  expected_channels?: string[]
}

export function listTasks(params?: TaskListParams): Promise<TaskListResponse> {
  return api.get<TaskListResponse>("/tasks/", params as ApiRequestOptions["params"])
}

export function createTask(payload: TaskCreatePayload): Promise<TaskItem> {
  return api.post<TaskItem>("/tasks/", payload)
}

/** GET /api/tasks/{taskId} — single task (for config-derived fields like last_analysis_at). */
export function getTask(taskId: number): Promise<TaskItem> {
  return api.get<TaskItem>(`/tasks/${taskId}`)
}

export function archiveTask(taskId: number): Promise<TaskItem> {
  return api.post<TaskItem>(`/tasks/${taskId}/archive`)
}

export function unarchiveTask(taskId: number): Promise<TaskItem> {
  return api.post<TaskItem>(`/tasks/${taskId}/unarchive`)
}

/** Soft-delete = archive (backend honors 不删减, never removes the row). */
export function deleteTask(taskId: number): Promise<void> {
  return api.delete<void>(`/tasks/${taskId}`)
}

/* =========================================================================
 * Dashboard API — types + helpers (S2 dashboard aggregation).
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/dashboard.py::DashboardData`.
 * ======================================================================= */

export interface DashboardKpis {
  active_tasks: number
  monthly_completed: number
  pending_alerts: number
  avg_audit_hours: number
}

export interface DashboardInProgressTask {
  id: number
  title: string
  /** 工号 — placeholder until S3 lands the employee_id field on Task. */
  employee_id?: string | null
  status: string
  /** Grayscale stage label (待开始/导入中/清洗中/已完成/失败/已取消/已暂停). */
  stage: string
  /** 0-100, rendered as a grayscale bar — never a colored progress bar. */
  progress: number
  updated_at: string
}

export interface DashboardRecentReport {
  id: number
  task_id: number
  task_title: string
  created_at: string
}

export interface DashboardPendingAction {
  id: number
  /** "review_pending" | "report_pending" — drives the action button label. */
  type: string
  title: string
  task_id: number
}

export interface DashboardData {
  kpis: DashboardKpis
  in_progress_tasks: DashboardInProgressTask[]
  recent_reports: DashboardRecentReport[]
  pending_actions: DashboardPendingAction[]
}

/** GET /api/dashboard — aggregated landing-page payload. */
export function getDashboard(): Promise<DashboardData> {
  return api.get<DashboardData>("/dashboard/")
}

/* =========================================================================
 * Document API — types + helpers (S4 data import).
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/tasks.py::DocumentResponse`.
 * ======================================================================= */

/**
 * Document status (backend documents.status).
 * pending / processing / completed / failed / deleted.
 */
export type DocumentStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "deleted"

/** One document row in the import page's file table. */
export interface DocumentItem {
  id: number
  filename: string
  original_path: string
  channel?: string | null
  status: DocumentStatus
  size_bytes?: number | null
  /** Stage-1 document portrait (account_type/holder/institution/...). Null
   *  when not yet generated. */
  portrait?: Record<string, unknown> | null
  created_at: string
  error_log?: string | null
}

export interface DocumentListResponse {
  items: DocumentItem[]
  total: number
}

/** Query params for GET /api/tasks/{id}/documents. */
export interface DocumentListParams {
  channel?: string
  include_deleted?: boolean
}

/** GET /api/tasks/{taskId}/documents — list files + parse status, optional channel filter. */
export function listDocuments(
  taskId: number,
  params?: DocumentListParams,
): Promise<DocumentListResponse> {
  return api.get<DocumentListResponse>(
    `/tasks/${taskId}/documents`,
    params as ApiRequestOptions["params"],
  )
}

/** GET /api/tasks/{taskId}/documents/{docId} — fetch one document with latest portrait. */
export function getDocument(taskId: number, docId: number): Promise<DocumentItem> {
  return api.get<DocumentItem>(`/tasks/${taskId}/documents/${docId}`)
}

/**
 * POST /api/tasks/{taskId}/append-upload (multipart) — append files to an
 * existing task with a channel label. `apiFetch` detects FormData and sends
 * multipart without a Content-Type header (browser sets the boundary).
 */
export function uploadTaskDocuments(
  taskId: number,
  files: File[],
  channel?: string,
): Promise<TaskItem> {
  const form = new FormData()
  for (const f of files) {
    form.append("files", f, f.name)
  }
  if (channel) {
    form.append("channel", channel)
  }
  return api.post<TaskItem>(`/tasks/${taskId}/append-upload`, form)
}

/**
 * POST /api/tasks/upload (multipart) — create a new task from uploaded files.
 * Used only when the import page needs to bootstrap a draft task; the common
 * path is `uploadTaskDocuments` against an existing task.
 */
export function createTaskFromUpload(
  title: string,
  files: File[],
  channel?: string,
): Promise<TaskItem> {
  const form = new FormData()
  form.append("title", title)
  for (const f of files) {
    form.append("files", f, f.name)
  }
  if (channel) {
    form.append("channel", channel)
  }
  return api.post<TaskItem>("/tasks/upload", form)
}

/** DELETE /api/tasks/{taskId}/documents/{docId} — soft-delete (status → deleted). */
export function deleteDocument(taskId: number, docId: number): Promise<void> {
  return api.delete<void>(`/tasks/${taskId}/documents/${docId}`)
}

/**
 * POST /api/tasks/{taskId}/start — manually kick off extraction for a draft task
 * (uploads no longer auto-start). Body optional; backend falls back to the
 * saved document_folder. Returns the running task.
 */
export function startExtraction(taskId: number): Promise<TaskItem> {
  return api.post<TaskItem>(`/tasks/${taskId}/start`, {})
}

/* =========================================================================
 * Cleaning / Standardization API — types + helpers (S5).
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/tasks.py::RecordResponse`.
 * 清洗不删减: standard + unparsed + excluded all persisted with raw_payload.
 * ======================================================================= */

/** record_type drives the cleaning page's tabs/filters. */
export type RecordType = "standard" | "unparsed" | "excluded"

/** status: active (default) | restored (捞回过 — row stays, 不删减). */
export type RecordStatus = "active" | "restored"

/** One flow_records row. raw_payload holds the original cells verbatim. */
export interface FlowRecordItem {
  id: number
  task_id: number
  document_id?: number | null
  channel?: string | null
  record_type: RecordType
  row_index: number
  is_valid: boolean
  transaction_time?: string | null
  counterparty_name?: string | null
  counterparty_account?: string | null
  amount?: string | null
  raw_amount?: string | null
  /** 账户余额（本笔交易后的账户余额；无余额列文档为空）. 06-28-balance-column-check. */
  balance?: string | null
  summary?: string | null
  transaction_type?: string | null
  raw_payload?: { cells?: string[] } | null
  status: RecordStatus
  exclude_reason?: string | null
  created_at: string
}

export interface RecordListResponse {
  items: FlowRecordItem[]
  total: number
  page: number
  page_size: number
}

/** Query params for GET /api/tasks/{id}/records. */
export interface RecordListParams {
  channel?: string
  /** standard | unparsed | excluded | all. Defaults to standard on the backend. */
  record_type?: RecordType | "all"
  page?: number
  page_size?: number
}

/** GET /api/tasks/{taskId}/records — paginated flow_records. */
export function listTaskRecords(
  taskId: number,
  params?: RecordListParams,
): Promise<RecordListResponse> {
  return api.get<RecordListResponse>(
    `/tasks/${taskId}/records`,
    params as ApiRequestOptions["params"],
  )
}

/** GET /api/tasks/{taskId}/records/{recordId} — single flow_record drill-down
 * (流水号弹窗用). Owner-checked server-side; returns raw_payload for 原始↔标准对照. */
export function getTaskRecord(
  taskId: number,
  recordId: number,
): Promise<FlowRecordItem> {
  return api.get<FlowRecordItem>(`/tasks/${taskId}/records/${recordId}`)
}

/** GET /api/tasks/{taskId}/excluded — excluded + unparsed, active only (可捞回).
 * `record_type` narrows to one type so the sub-tabs paginate independently. */
export function listExcluded(
  taskId: number,
  params?: { page?: number; page_size?: number; record_type?: RecordType },
): Promise<RecordListResponse> {
  return api.get<RecordListResponse>(
    `/tasks/${taskId}/excluded`,
    params as ApiRequestOptions["params"],
  )
}

/** POST /api/tasks/{taskId}/records/{recordId}/restore — mark a row restored (捞回). */
export function restoreRecord(
  taskId: number,
  recordId: number,
): Promise<FlowRecordItem> {
  return api.post<FlowRecordItem>(`/tasks/${taskId}/records/${recordId}/restore`)
}

/** POST /api/tasks/{taskId}/cleaning/commit — lock the standard snapshot. */
export function commitCleaning(taskId: number): Promise<TaskItem> {
  return api.post<TaskItem>(`/tasks/${taskId}/cleaning/commit`)
}

/**
 * GET /api/tasks/{taskId}/cleaning/export — download the unparsed/excluded log.
 * Returns the raw Response (file stream); the caller triggers a browser download.
 */
export function exportCleaningLog(
  taskId: number,
  format: "csv" | "json" = "csv",
): Promise<Response> {
  return apiFetch<Response>(
    `/tasks/${taskId}/cleaning/export`,
    { method: "GET", params: { format } },
  )
}

/* =========================================================================
 * AI Analysis API — types + helpers (S6).
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/tasks.py` S6 block + `app/llm/types.py`.
 * agent 接入点结构遵循 docs/research/pydantic-ai-conventions.md (v1.107.0)：
 * AuditDeps / @agent.tool / ModelMessagesTypeAdapter / message_history.
 * 本切片 agent.run / chat 走占位实现（真实 prompt/tools 用户后续接）。
 * ======================================================================= */

/** severity 三态，前端灰阶+形状双编码（单色原则，禁红黄绿）. */
export type Severity = "high" | "medium" | "low"

/** status 三态：pending（默认）/ accepted（采纳为告警）/ ignored（忽略）. */
export type FindingStatus = "pending" | "accepted" | "ignored"

/** One findings row — AI-surfaced anomaly + 人工复核状态.
 *  Mirrors `backend/app/routers/tasks.py::FindingResponse`.
 *  06-26-ai-agent additive 字段（dimension_id / detail_text /
 *  evidence_record_ids / source）向后兼容，历史 finding 为空. */
export interface FindingItem {
  id: number
  task_id: number
  type: string
  severity: Severity
  description: string
  counterparty?: string | null
  amount?: string | null
  confidence: number
  status: FindingStatus
  comment?: string | null
  /** 命中的维度 id（维度 agent 跑出，source='rule'）. */
  dimension_id?: number | null
  /** 维度 agent 的自然语言分析正文（右侧详情正文）. */
  detail_text?: string | null
  /** 命中的 flow_record id 列表（关联记录下钻）. */
  evidence_record_ids?: number[] | null
  /** 来源：rule（维度跑出）| balance_check（余额校验）| 历史占位. */
  source?: string | null
  /** 关联文档 id（余额校验 finding 关联文档；维度 finding 为 null）. 06-28-balance-column-check. */
  document_id?: number | null
  created_at: string
  updated_at: string
}

export interface FindingListResponse {
  items: FindingItem[]
  total: number
}

/** Query params for GET /api/tasks/{id}/findings.
 *  `source` 过滤：传 "balance_check" 单取余额校验 finding；不传则排除 balance_check（AI 分析页用）. */
export interface FindingListParams {
  severity?: Severity
  status?: FindingStatus
  source?: string
}

/** POST /api/tasks/{id}/analyze 响应：异步启动确认（status=started + 维度数）.
 *  后台串行跑 enabled 维度，进度走 WebSocket event=analysis.progress（前端
 *  无 WS token 通道时改轮询 findings + task.config.last_analysis_summary）. */
export interface AnalyzeResponse {
  status: string
  task_id: number
  total_dimensions: number
}

/** POST /api/tasks/{id}/analyze 请求体（占位，无必填字段；mode 兼容旧前端）. */
export interface AnalyzeRequest {
  mode?: "quick" | "deep"
}

/** 单次工具调用痕迹（追问 agent 调只读工具时，前端气泡小字「🔍 已查询：…」）.
 *  Mirrors `backend/app/schemas/audit.py::ChatToolTrace`. */
export interface ChatToolTrace {
  tool: string
  summary: string
}

/** 本轮流问沉淀出的草稿维度（前端气泡「已沉淀维度：XXX（草稿，待启用）」）.
 *  Mirrors `backend/app/schemas/audit.py::ChatSedimentedDimension`. */
export interface ChatSedimentedDimension {
  name: string
  severity: DimensionSeverity
}

/** POST /api/tasks/{id}/analyze/chat 响应（含 conversation_id，多会话）.
 *  ``tool_traces`` / ``sedimented_dimension`` 为 06-26-ai-agent 新增（向后
 *  兼容旧前端：均可选，缺省空/None）。Mirrors `ChatResponse`. */
export interface ChatResponse {
  reply: string
  conversation_id: number
  tool_traces?: ChatToolTrace[]
  sedimented_dimension?: ChatSedimentedDimension | null
}

/** POST /api/tasks/{id}/analyze/chat 请求体（message + conversation_id）. */
export interface ChatRequest {
  message: string
  conversation_id?: number | null
}

/** PATCH /api/findings/{id} 请求体（status / comment，均可选）. */
export interface PatchFindingRequest {
  status?: FindingStatus
  comment?: string
}

/** task.config.last_analysis_summary —— 后台跑分析回填的进度摘要.
 *  后端每跑完一个维度增量写 {total_dimensions, completed, findings, status}，
 *  跑完写 status=finished + details. 前端进度条按 completed/total_dimensions
 *  算百分比（PRD §十一 确定式进度条），status=finished 满格收尾. */
export interface LastAnalysisSummary {
  total_dimensions: number
  completed: number
  findings: number
  status?: "running" | "finished"
  details?: string[]
}

/** GET /api/tasks/{taskId}/findings — severity + status filter, severity-desc sorted. */
export function listFindings(
  taskId: number,
  params?: FindingListParams,
): Promise<FindingListResponse> {
  return api.get<FindingListResponse>(
    `/tasks/${taskId}/findings`,
    params as ApiRequestOptions["params"],
  )
}

/** POST /api/tasks/{taskId}/analyze — 异步触发 AI 分析（立即返 started + 维度数）.
 *  后台串行跑 enabled 维度，进度走 WS analysis.progress；finding 实时增量入库.
 *  重跑只删 pending finding，保留 accepted/ignored 人工结论. */
export function startAnalysis(
  taskId: number,
  body?: AnalyzeRequest,
): Promise<AnalyzeResponse> {
  return api.post<AnalyzeResponse>(`/tasks/${taskId}/analyze`, body ?? {})
}

/** PATCH /api/findings/{findingId} — update finding status/comment (top-level, no /tasks prefix). */
export function patchFinding(
  findingId: number,
  body: PatchFindingRequest,
): Promise<FindingItem> {
  return api.patch<FindingItem>(`/findings/${findingId}`, body)
}

/** POST /api/tasks/{taskId}/analyze/chat — 多轮追问（带 conversation_id；首轮流建会话）. */
export function chatAnalyze(
  taskId: number,
  message: string,
  conversationId?: number | null,
): Promise<ChatResponse> {
  const body: ChatRequest = { message }
  if (conversationId != null) body.conversation_id = conversationId
  return api.post<ChatResponse>(`/tasks/${taskId}/analyze/chat`, body)
}

/* =========================================================================
 * Report API — types + helpers (S7 审查报告闭环).
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/reports.py` + `app/schemas/review.py`.
 * 章节化审查报告：8 章 ReportChapter + 章节级批注 ReportAnnotation +
 * status(draft|generating|generated|failed|final). 单色原则 + 不删减精神（定稿只改软态）.
 * ======================================================================= */

/** 报告软态：generating 后台生成中；final 整报告只读，写操作 409. */
export type ReportStatus =
  | "draft"
  | "generating"
  | "generated"
  | "failed"
  | "final"

/** One chapter of a chaptered review report (S7). Mirrors ReportChapterResponse. */
export interface ReportChapterItem {
  id: number
  report_id: number
  title: string
  content: string
  order_index: number
  generated_at: string
}

/** One review annotation on a report chapter (S7). Mirrors ReportAnnotationResponse. */
export interface ReportAnnotationItem {
  id: number
  report_id: number
  chapter_id?: number | null
  author: string
  content: string
  resolved: boolean
  created_at: string
}

/** 报告 + chapters（按 order_index 排序）+ annotations. Mirrors ReportResponse. */
export interface ReportDetail {
  id: number
  task_id: number
  review_id?: number | null
  format: string
  content_path: string
  content: string
  status: ReportStatus
  chapters: ReportChapterItem[]
  annotations: ReportAnnotationItem[]
  created_at: string
}

/** PATCH /api/reports/{id}/chapters/{cid} 请求体（行内编辑 content）. */
export interface ReportChapterPatchBody {
  content: string
}

/** reorder 单项：chapter_id + 新 order_index. */
export interface ReportChapterReorderItem {
  chapter_id: number
  order_index: number
}

/** POST /api/reports/{id}/annotations 请求体（章节级批注，chapter_id 可选）. */
export interface ReportAnnotationCreateBody {
  chapter_id?: number | null
  content: string
}

/** POST /api/tasks/{taskId}/report — 章节化生成（幂等：已有则返已有）. */
export function generateReport(taskId: number): Promise<ReportDetail> {
  return api.post<ReportDetail>(`/tasks/${taskId}/report`)
}

/** GET /api/tasks/{taskId}/report — 取当前报告 + chapters + annotations. */
export function getReport(taskId: number): Promise<ReportDetail> {
  return api.get<ReportDetail>(`/tasks/${taskId}/report`)
}

/** PATCH /api/reports/{id}/chapters/{cid} — 编辑章节 content（定稿 409）. */
export function patchChapter(
  reportId: number,
  chapterId: number,
  body: ReportChapterPatchBody,
): Promise<ReportChapterItem> {
  return api.patch<ReportChapterItem>(
    `/reports/${reportId}/chapters/${chapterId}`,
    body,
  )
}

/** POST /api/reports/{id}/chapters/{cid}/regenerate — 单章重生成（定稿 409）. */
export function regenerateChapter(
  reportId: number,
  chapterId: number,
): Promise<ReportChapterItem> {
  return api.post<ReportChapterItem>(
    `/reports/${reportId}/chapters/${chapterId}/regenerate`,
  )
}

/** POST /api/reports/{id}/chapters/reorder — 拖拽排序（定稿 409）. */
export function reorderChapters(
  reportId: number,
  items: ReportChapterReorderItem[],
): Promise<ReportDetail> {
  return api.post<ReportDetail>(`/reports/${reportId}/chapters/reorder`, items)
}

/** POST /api/reports/{id}/regenerate — 全报告重生成（定稿 409）. */
export function regenerateReport(reportId: number): Promise<ReportDetail> {
  return api.post<ReportDetail>(`/reports/${reportId}/regenerate`)
}

/** POST /api/reports/{id}/annotations — 新建批注（定稿 409）. */
export function createAnnotation(
  reportId: number,
  body: ReportAnnotationCreateBody,
): Promise<ReportAnnotationItem> {
  return api.post<ReportAnnotationItem>(
    `/reports/${reportId}/annotations`,
    body,
  )
}

/** PATCH /api/reports/{id}/annotations/{aid} — 切 resolved（定稿 409）. */
export function toggleAnnotation(
  reportId: number,
  annotationId: number,
): Promise<ReportAnnotationItem> {
  return api.patch<ReportAnnotationItem>(
    `/reports/${reportId}/annotations/${annotationId}`,
  )
}

/** POST /api/reports/{id}/finalize — 定稿 status→final. */
export function finalizeReport(reportId: number): Promise<ReportDetail> {
  return api.post<ReportDetail>(`/reports/${reportId}/finalize`)
}

/* =========================================================================
 * Export API — S8 导出扩展（报告多格式 + 数据多范围 + 历史 + 预览）.
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/exports.py` + `app/schemas/review.py`.
 * 不删减精神：导出只读原数据 + 复制产物；导出历史产物保留可重新下载.
 * ======================================================================= */

/** 导出范围：report=报告多格式 / raw=原始流 / standard=标准化流 / findings=异常. */
export type ExportScope = "report" | "raw" | "standard" | "findings"

/** 报告导出格式：pdf / docx / html. */
export type ReportExportFormat = "pdf" | "html"

/** 数据导出格式：excel / csv. */
export type DataExportFormat = "excel" | "csv"

/** ExportResponse — mirrors backend ExportResponse（含 scope）. */
export interface ExportItem {
  id: number
  task_id: number
  review_id?: number | null
  format: string
  scope?: ExportScope | null
  file_path: string
  created_at: string
}

/** POST /tasks/{id}/export/report 请求体. */
export interface ReportExportBody {
  format: ReportExportFormat
  include_annotations: boolean
}

/** POST /tasks/{id}/export/data 请求体. */
export interface DataExportBody {
  scope: "raw" | "standard" | "findings"
  format: DataExportFormat
}

/** 导出历史列表单项（GET /tasks/{id}/exports）. */
export interface ExportListItem {
  id: number
  task_id: number
  review_id?: number | null
  format: string
  scope?: ExportScope | null
  file_path: string
  created_at: string
}

/** 预览取样响应（GET /tasks/{id}/export/preview）. */
export interface ExportPreview {
  scope: ExportScope
  sample: unknown
  annotation_count?: number | null
}

/** POST /tasks/{taskId}/export/report — 报告多格式导出（pdf/docx/html）. */
export function exportTaskReport(
  taskId: number,
  body: ReportExportBody,
): Promise<ExportItem> {
  return api.post<ExportItem>(`/tasks/${taskId}/export/report`, body)
}

/** POST /tasks/{taskId}/export/data — 数据多范围导出（raw/standard/findings × excel/csv）. */
export function exportTaskData(
  taskId: number,
  body: DataExportBody,
): Promise<ExportItem> {
  return api.post<ExportItem>(`/tasks/${taskId}/export/data`, body)
}

/** GET /tasks/{taskId}/exports — 导出历史列表（按 created_at 降序）. */
export function listTaskExports(taskId: number): Promise<ExportListItem[]> {
  return api.get<ExportListItem[]>(`/tasks/${taskId}/exports`)
}

/** GET /tasks/{taskId}/export/preview?scope=... — 取样预览（不生成产物）. */
export function previewTaskExport(
  taskId: number,
  scope: ExportScope,
): Promise<ExportPreview> {
  return api.get<ExportPreview>(
    `/tasks/${taskId}/export/preview`,
    { scope } as ApiRequestOptions["params"],
  )
}

/** GET /api/exports/{exportId}/download — 下载产物（返 raw Response，调用方触发浏览器下载）. */
export function downloadExport(exportId: number): Promise<Response> {
  return apiFetch<Response>(`/exports/${exportId}/download`, { method: "GET" })
}

/* =========================================================================
 * Settings + User API — S8 设置页（4 Tab）+ 改密码 + 改个人信息.
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/settings.py` + `auth.py` + `users.py`.
 * ======================================================================= */

/** 设置项 type：string | number | boolean | select. */
export type SettingType = "string" | "number" | "boolean" | "select"

/** GET /api/settings/schema 单项元数据. */
export interface SettingSchemaItem {
  key: string
  category: string
  type: SettingType
  label: string
  description: string
  value: string
  options?: string[]
}

/** GET /api/settings/ 单项（已存值）. */
export interface SettingItem {
  key: string
  value: string
  category: string
  updated_at: string
  updated_by: number
}

/** POST /api/auth/change-password 请求体. */
export interface ChangePasswordBody {
  old_password: string
  new_password: string
}

/** PATCH /api/users/me 请求体（个人信息，当前用户改自己）. */
export interface UpdateMeBody {
  username?: string
  email?: string
}

/** GET /api/auth/me + PATCH /api/users/me 响应 — mirrors UserResponse.
 *  (Duplicates the shape in use-current-user.ts to avoid a circular import;
 *  the hook re-exports its own CurrentUser that is structurally identical.) */
export interface UserMeResponse {
  id: number
  username: string
  email: string
  role: string
  is_active: boolean
}

/** GET /api/settings/schema — 设置项元数据列表（供前端表单渲染）. */
export function getSettingsSchema(): Promise<SettingSchemaItem[]> {
  return api.get<SettingSchemaItem[]>("/settings/schema")
}

/** GET /api/settings/ — 所有设置项已存值. */
export function listSettings(): Promise<SettingItem[]> {
  return api.get<SettingItem[]>("/settings/")
}

/** PUT /api/settings/{key} — 更新单个设置项. */
export function updateSetting(
  key: string,
  value: string,
): Promise<SettingItem> {
  return api.put<SettingItem>(`/settings/${encodeURIComponent(key)}`, { value })
}

/** POST /api/auth/change-password — 改密码（校验旧密码 + 新密码长度≥8）. */
export function changePassword(body: ChangePasswordBody): Promise<{ ok: boolean }> {
  return api.post<{ ok: boolean }>("/auth/change-password", body)
}

/** PATCH /api/users/me — 当前用户改个人信息（username/email，非 admin-only）. */
export function updateMe(body: UpdateMeBody): Promise<UserMeResponse> {
  return api.patch<UserMeResponse>("/users/me", body)
}

/* =========================================================================
 * LLM Model Cards + Stage Assignments API — 06-23-llm-model-card.
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/llm_models.py` + `app/schemas/llm_model.py`.
 * 模型卡片管理 + 按阶段指派；api_key 脱敏（********XXXX），编辑留空不改.
 * ======================================================================= */

/** reasoning 预算档位（off=不传 reasoning_effort；reasoning 模型默认 low）. */
export type ThinkingLevel = "off" | "low" | "medium" | "high"

/** 6 个阶段：classification / portrait / normalization / ai_analysis / ai_qa / report_generation. */
export type Stage =
  | "classification"
  | "portrait"
  | "normalization"
  | "ai_analysis"
  | "ai_qa"
  | "report_generation"

/** 模型卡片响应——api_key 脱敏（********XXXX）. */
export interface LLMModel {
  id: number
  display_name: string
  model_name: string
  provider_base_url: string
  /** 脱敏串（********XXXX）；编辑时留空/传脱敏串表示不改原值. */
  api_key: string
  context_length: number
  max_output: number
  supports_tool_call: boolean
  supports_tool_choice_required: boolean
  is_reasoning: boolean
  supports_streaming: boolean
  default_thinking: ThinkingLevel
  default_max_tokens: number
  default_temperature?: number | null
  created_at: string
  updated_at: string
}

/** 新建/编辑模型卡片请求体（api_key 留空不改）. */
export interface LLMModelUpsertBody {
  display_name: string
  model_name: string
  provider_base_url: string
  /** 留空/省略/传脱敏串 → 不改原值；新建默认空串. */
  api_key?: string
  context_length: number
  max_output: number
  supports_tool_call: boolean
  supports_tool_choice_required: boolean
  is_reasoning: boolean
  supports_streaming: boolean
  default_thinking: ThinkingLevel
  default_max_tokens: number
  default_temperature?: number | null
}

/** 阶段指派响应——stage + 指派的卡片（未指派时 llm_model=null）. */
export interface LLMModelAssignment {
  id?: number | null
  stage: Stage
  llm_model_id?: number | null
  llm_model?: LLMModel | null
  created_at?: string | null
  updated_at?: string | null
}

/** PUT /api/llm-model-assignments/{stage} 请求体（llm_model_id=null 解除指派）. */
export interface LLMModelAssignmentBody {
  llm_model_id: number | null
}

/** GET /api/llm-models — 列出所有模型卡片（api_key 脱敏）. */
export function listLLMModels(): Promise<LLMModel[]> {
  return api.get<LLMModel[]>("/llm-models")
}

/** POST /api/llm-models — 新建模型卡片（admin）. */
export function createLLMModel(body: LLMModelUpsertBody): Promise<LLMModel> {
  return api.post<LLMModel>("/llm-models", body)
}

/** PUT /api/llm-models/{id} — 更新模型卡片（admin；api_key 留空不改）. */
export function updateLLMModel(id: number, body: LLMModelUpsertBody): Promise<LLMModel> {
  return api.put<LLMModel>(`/llm-models/${id}`, body)
}

/** DELETE /api/llm-models/{id} — 删除模型卡片（admin；被指派返 409，force=true 解除指派后删）. */
export function deleteLLMModel(id: number, force: boolean = false): Promise<void> {
  return api.delete<void>(`/llm-models/${id}${force ? "?force=true" : ""}`)
}

/** GET /api/llm-model-assignments — 列出 6 阶段 + 各自指派. */
export function listLLMModelAssignments(): Promise<LLMModelAssignment[]> {
  return api.get<LLMModelAssignment[]>("/llm-model-assignments")
}

/** PUT /api/llm-model-assignments/{stage} — 指派/解除该阶段的卡片（admin）. */
export function upsertLLMModelAssignment(
  stage: Stage,
  body: LLMModelAssignmentBody,
): Promise<LLMModelAssignment> {
  return api.put<LLMModelAssignment>(`/llm-model-assignments/${stage}`, body)
}

/* =========================================================================
 * Keyword Library + Keyword Review API — 06-23-tab.
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/keyword_library.py` + `tasks.py` keyword-review block.
 * 全局关键词库（卡片 CRUD + excel 导入/导出）+ 任务级关键词审查（run/hits/patch）.
 * ======================================================================= */

/** 卡片级风险等级（词级无风险等级）. */
export type KeywordRiskLevel = "高" | "中" | "低"

/** 命中匹配类型（对齐 backend matcher.MatchType.value）. */
export type KeywordMatchType = "精确匹配" | "脱敏匹配" | "模糊匹配"

/** 命中字段（只扫 standard 记录的这两列）. */
export type KeywordMatchedField = "counterparty_name" | "summary"

/** 命中人工处理状态. */
export type KeywordHitStatus = "pending" | "confirmed" | "ignored"

/** 单个关键词（详情用）. */
export interface KeywordTermItem {
  id: number
  term: string
  created_at: string
}

/** 卡片列表项（含 term 数 + 风险等级 + 备注）. */
export interface KeywordCardListItem {
  id: number
  name: string
  risk_level: KeywordRiskLevel
  note?: string | null
  term_count: number
  created_at: string
  updated_at: string
}

/** 卡片详情（含 terms 列表）. */
export interface KeywordCardDetail {
  id: number
  name: string
  risk_level: KeywordRiskLevel
  note?: string | null
  terms: KeywordTermItem[]
  created_at: string
  updated_at: string
}

/** 新建/编辑卡片请求体（terms 全量替换；编辑时可不传 terms = 不改现有词）. */
export interface KeywordCardUpsertBody {
  name: string
  risk_level: KeywordRiskLevel
  note?: string | null
  terms?: string[]
}

/** excel 导入统计. */
export interface KeywordImportStats {
  created_cards: number
  appended_cards: number
  new_terms: number
  skipped_terms: number
  rejected_rows: number
}

/** POST /tasks/{id}/keyword-review/run 请求体. */
export interface KeywordReviewRunBody {
  card_ids: number[]
}

/** POST run 响应统计. */
export interface KeywordReviewRunStats {
  scanned_records: number
  hit_records: number
  hit_terms: number
  high_risk_hits: number
}

/** 单个命中行. */
export interface KeywordHitItem {
  id: number
  task_id: number
  flow_record_id: number
  keyword_card_id: number
  keyword_term_id: number
  match_type: KeywordMatchType
  confidence: number
  risk_level: KeywordRiskLevel
  matched_field: KeywordMatchedField
  matched_snippet: string
  status: KeywordHitStatus
  note?: string | null
  created_at: string
  updated_at: string
}

/** 命中分页列表. */
export interface KeywordHitListResponse {
  items: KeywordHitItem[]
  total: number
  page: number
  page_size: number
}

/** PATCH 命中请求体（status / note，均可选）. */
export interface KeywordHitPatchBody {
  status?: KeywordHitStatus
  note?: string
}

/** GET /api/keyword-library/cards — 列出卡片（所有登录用户可读）. */
export function listKeywordCards(): Promise<KeywordCardListItem[]> {
  return api.get<KeywordCardListItem[]>("/keyword-library/cards")
}

/** GET /api/keyword-library/cards/{id} — 卡片详情. */
export function getKeywordCard(cardId: number): Promise<KeywordCardDetail> {
  return api.get<KeywordCardDetail>(`/keyword-library/cards/${cardId}`)
}

/** POST /api/keyword-library/cards — 新建卡片（admin）. */
export function createKeywordCard(body: KeywordCardUpsertBody): Promise<KeywordCardDetail> {
  return api.post<KeywordCardDetail>("/keyword-library/cards", body)
}

/** PUT /api/keyword-library/cards/{id} — 编辑卡片（admin；terms 全量替换）. */
export function updateKeywordCard(
  cardId: number,
  body: KeywordCardUpsertBody,
): Promise<KeywordCardDetail> {
  return api.put<KeywordCardDetail>(`/keyword-library/cards/${cardId}`, body)
}

/** DELETE /api/keyword-library/cards/{id} — 删卡（admin；被引用返 409）. */
export function deleteKeywordCard(cardId: number): Promise<void> {
  return api.delete<void>(`/keyword-library/cards/${cardId}`)
}

/**
 * POST /api/keyword-library/import — excel 导入（admin，multipart）.
 * `apiFetch` detects FormData and sends multipart without a Content-Type header.
 */
export function importKeywordLibrary(file: File): Promise<KeywordImportStats> {
  const form = new FormData()
  form.append("file", file, file.name)
  return api.post<KeywordImportStats>("/keyword-library/import", form)
}

/**
 * GET /api/keyword-library/export — excel 导出（返 raw Response，调用方触发下载）.
 */
export function exportKeywordLibrary(): Promise<Response> {
  return apiFetch<Response>("/keyword-library/export", { method: "GET" })
}

/** POST /api/tasks/{taskId}/keyword-review/run — 运行关键词审查（owner）. */
export function runKeywordReview(
  taskId: number,
  body: KeywordReviewRunBody,
): Promise<KeywordReviewRunStats> {
  return api.post<KeywordReviewRunStats>(
    `/tasks/${taskId}/keyword-review/run`,
    body,
  )
}

/** GET /api/tasks/{taskId}/keyword-review/hits — 分页列命中（支持过滤）. */
export function listKeywordHits(
  taskId: number,
  params?: {
    status?: KeywordHitStatus
    risk_level?: KeywordRiskLevel
    match_type?: KeywordMatchType
    page?: number
    page_size?: number
  },
): Promise<KeywordHitListResponse> {
  return api.get<KeywordHitListResponse>(
    `/tasks/${taskId}/keyword-review/hits`,
    params as ApiRequestOptions["params"],
  )
}

/** PATCH /api/tasks/{taskId}/keyword-review/hits/{hitId} — 改命中 status / note. */
export function patchKeywordHit(
  taskId: number,
  hitId: number,
  body: KeywordHitPatchBody,
): Promise<KeywordHitItem> {
  return api.patch<KeywordHitItem>(
    `/tasks/${taskId}/keyword-review/hits/${hitId}`,
    body,
  )
}

/* =========================================================================
 * Audit Dimensions + Analysis Conversations API — 06-26-ai-agent.
 * Appended only; the apiFetch core above is unchanged.
 * Mirrors `backend/app/routers/audit_dimensions.py` + `tasks.py` analyze block
 * + `app/schemas/audit.py`. 维度 = 结构化提示词（CRUD 落库）；追问会话多轮.
 * ======================================================================= */

/** 维度 severity（对齐 backend DIMENSION_SEVERITIES）. */
export type DimensionSeverity = "high" | "medium" | "low"

/** 维度来源：system（迁移 seed）/ agent（create_dimension 沉淀草稿）. */
export type DimensionSource = "system" | "agent"

/** 维度步骤项 {tool, params}（steps.tool 限只读工具白名单）. */
export interface DimensionStep {
  tool: string
  params?: Record<string, unknown>
}

/** 维度列表项. */
export interface AuditDimensionListItem {
  id: number
  name: string
  source: DimensionSource
  purpose: string
  severity: DimensionSeverity
  enabled: boolean
  created_by?: number | null
  created_at: string
  updated_at: string
}

/** 维度详情（含 steps / judgment / prompt 成品缓存）. */
export interface AuditDimensionDetail {
  id: number
  name: string
  source: DimensionSource
  purpose: string
  steps: DimensionStep[]
  judgment: string
  severity: DimensionSeverity
  prompt: string
  enabled: boolean
  created_by?: number | null
  created_at: string
  updated_at: string
}

/** 新建维度请求体（admin；source 默认 system，enabled 默认 true）. */
export interface AuditDimensionCreateBody {
  name: string
  purpose: string
  steps: DimensionStep[]
  judgment: string
  severity: DimensionSeverity
  source?: DimensionSource
  enabled?: boolean
}

/** 编辑维度请求体（所有字段可选；任一字段变化时后端重拼 prompt）. */
export interface AuditDimensionUpdateBody {
  name?: string
  purpose?: string
  steps?: DimensionStep[]
  judgment?: string
  severity?: DimensionSeverity
  enabled?: boolean
}

/** 追问会话列表项. */
export interface ConversationItem {
  id: number
  title: string
  created_at: string
  updated_at: string
}

/** 会话列表响应. */
export interface ConversationListResponse {
  items: ConversationItem[]
  total: number
}

/** 会话历史中抽取出的单条可读消息（GET 会话历史）.
 *  role: user（用户提问）/ ai（追问 agent 回复）。Mirrors `ConversationMessage`. */
export interface ConversationMessage {
  role: "user" | "ai"
  text: string
}

/** GET 会话历史响应：会话 + 抽取后的消息历史（点历史会话回放到聊天面板）.
 *  Mirrors `backend/app/schemas/audit.py::ConversationDetail`. */
export interface ConversationDetail {
  id: number
  title: string
  messages: ConversationMessage[]
  created_at: string
  updated_at: string
}

/** GET /api/audit-dimensions — 列维度（所有登录用户可读）. */
export function listAuditDimensions(): Promise<AuditDimensionListItem[]> {
  return api.get<AuditDimensionListItem[]>("/audit-dimensions")
}

/** GET /api/audit-dimensions/{id} — 维度详情（含 steps / judgment / prompt）. */
export function getAuditDimension(id: number): Promise<AuditDimensionDetail> {
  return api.get<AuditDimensionDetail>(`/audit-dimensions/${id}`)
}

/** POST /api/audit-dimensions — 新建维度（admin）. */
export function createAuditDimension(
  body: AuditDimensionCreateBody,
): Promise<AuditDimensionDetail> {
  return api.post<AuditDimensionDetail>("/audit-dimensions", body)
}

/** PUT /api/audit-dimensions/{id} — 编辑维度（admin）. */
export function updateAuditDimension(
  id: number,
  body: AuditDimensionUpdateBody,
): Promise<AuditDimensionDetail> {
  return api.put<AuditDimensionDetail>(`/audit-dimensions/${id}`, body)
}

/** DELETE /api/audit-dimensions/{id} — 删维度（admin；删 system 需 admin，
 *  删 agent 建的需 owner/admin；已被 finding 引用返 409）. */
export function deleteAuditDimension(id: number): Promise<void> {
  return api.delete<void>(`/audit-dimensions/${id}`)
}

/** GET /api/tasks/{taskId}/analyze/conversations — 列追问会话（按 id 升序）. */
export function listConversations(taskId: number): Promise<ConversationListResponse> {
  return api.get<ConversationListResponse>(
    `/tasks/${taskId}/analyze/conversations`,
  )
}

/** GET /api/tasks/{taskId}/analyze/conversations/{conversationId} — 取会话历史.
 *  点历史会话时调用：把 message_history 抽成 [{role, text}] 回放到聊天面板，
 *  可在其上继续追问（chatAnalyze 带 conversation_id）. */
export function getConversationHistory(
  taskId: number,
  conversationId: number,
): Promise<ConversationDetail> {
  return api.get<ConversationDetail>(
    `/tasks/${taskId}/analyze/conversations/${conversationId}`,
  )
}

/** POST /api/tasks/{taskId}/analyze/conversations — 新建会话（title 缺省由首问题定）. */
export function createConversation(
  taskId: number,
  title?: string,
): Promise<ConversationItem> {
  return api.post<ConversationItem>(
    `/tasks/${taskId}/analyze/conversations`,
    { title: title ?? null },
  )
}

/** DELETE /api/tasks/{taskId}/analyze/conversations/{id} — 删会话（只删历史，不影响沉淀维度）. */
export function deleteConversation(
  taskId: number,
  conversationId: number,
): Promise<void> {
  return api.delete<void>(
    `/tasks/${taskId}/analyze/conversations/${conversationId}`,
  )
}
