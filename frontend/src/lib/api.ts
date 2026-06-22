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
