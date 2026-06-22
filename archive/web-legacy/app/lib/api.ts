/**
 * API client with JWT authentication
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public data?: unknown
  ) {
    super(`API Error: ${status} ${statusText}`);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

export function setToken(token: string): void {
  localStorage.setItem("auth_token", token);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("refresh_token");
}

export function setRefreshToken(token: string): void {
  localStorage.setItem("refresh_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("refresh_token");
}

export interface ApiRequestOptions extends RequestInit {
  params?: Record<string, string>;
}

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error("No refresh token");
  }

  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    clearToken();
    throw new Error("Refresh failed");
  }

  const data = await response.json();
  setToken(data.access_token);
  setRefreshToken(data.refresh_token);
  return data.access_token;
}

export async function apiFetch<T>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const { params, ...fetchOptions } = options;

  let url = `${API_BASE}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  let response = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  const isRefreshEndpoint = endpoint === "/api/auth/login" || endpoint === "/api/auth/refresh";

  // Handle 401 by attempting token refresh. Keep /auth/me eligible so route guards can recover expired access tokens.
  if (response.status === 401 && !isRefreshEndpoint) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }

    try {
      const newToken = await refreshPromise;
      (headers as Record<string, string>)["Authorization"] = `Bearer ${newToken}`;
      response = await fetch(url, {
        ...fetchOptions,
        headers,
      });
    } catch {
      // Refresh failed, fall through to throw original error
    }
  }

  if (!response.ok) {
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      // Response may not be JSON
    }
    throw new ApiError(response.status, response.statusText, data);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Convenience methods
export const api = {
  get: <T>(endpoint: string, params?: Record<string, string>) =>
    apiFetch<T>(endpoint, { method: "GET", params }),

  post: <T>(endpoint: string, body?: unknown) =>
    apiFetch<T>(endpoint, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  put: <T>(endpoint: string, body?: unknown) =>
    apiFetch<T>(endpoint, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(endpoint: string, body?: unknown) =>
    apiFetch<T>(endpoint, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(endpoint: string) =>
    apiFetch<T>(endpoint, { method: "DELETE" }),
};

/**
 * POST a multipart/form-data request (file uploads + form fields).
 * Uses fetch directly because apiFetch forces JSON Content-Type.
 * Token refresh on 401 mirrors apiFetch.
 */
export async function uploadForm<T>(
  endpoint: string,
  formData: FormData
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const buildHeaders = (): HeadersInit => {
    // Let the browser set the multipart Content-Type + boundary.
    const headers: HeadersInit = {};
    const token = getToken();
    if (token) {
      (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  };

  let response = await fetch(url, { method: "POST", headers: buildHeaders(), body: formData });

  if (response.status === 401) {
    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      await refreshPromise;
      response = await fetch(url, { method: "POST", headers: buildHeaders(), body: formData });
    } catch {
      // fall through to throw original 401
    }
  }

  if (!response.ok) {
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      // non-JSON error
    }
    throw new ApiError(response.status, response.statusText, data);
  }
  return response.json();
}

/**
 * Download a binary file from an authenticated GET endpoint.
 * Fetches with the Bearer token (apiFetch cannot return blobs), then triggers
 * a browser download using the filename from the Content-Disposition header
 * or a fallback derived from the endpoint.
 */
export async function downloadFile(endpoint: string, fallbackName: string): Promise<void> {
  const url = `${API_BASE}${endpoint}`;
  const buildHeaders = (): HeadersInit => {
    const headers: HeadersInit = {};
    const token = getToken();
    if (token) {
      (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  };

  let response = await fetch(url, { headers: buildHeaders() });

  // Mirror apiFetch: retry once after refreshing an expired access token.
  if (response.status === 401) {
    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      await refreshPromise;
      response = await fetch(url, { headers: buildHeaders() });
    } catch {
      // Refresh failed — fall through to throw the original 401.
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = parseFilenameFromDisposition(disposition) || fallbackName;
  triggerBrowserDownload(blob, filename);
}

function parseFilenameFromDisposition(disposition: string): string | null {
  // RFC 5987 filename*=UTF-8''<value> first, then plain filename="...".
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(disposition);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      return star[1].trim();
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  if (plain) {
    return plain[1].trim();
  }
  return null;
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}
