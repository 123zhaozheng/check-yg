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
