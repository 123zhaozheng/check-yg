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
 */

const API_BASE = "/api"

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

/**
 * Core fetch wrapper. Sends cookies, handles JSON, throws ApiError on non-2xx,
 * and redirects to /login on 401 (auth cookie missing or expired).
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

  const response = await fetch(buildUrl(endpoint, params), {
    ...rest,
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    headers: finalHeaders,
    credentials: "include",
  })

  if (response.status === 401 && typeof window !== "undefined") {
    const current = window.location.pathname + window.location.search
    if (!current.startsWith("/login")) {
      window.location.replace(`/login?redirect=${encodeURIComponent(current)}`)
    }
    throw new ApiError(401, "Unauthorized")
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
