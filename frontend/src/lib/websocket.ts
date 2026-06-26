/**
 * Authenticated WebSocket client (06-26-ai-agent).
 *
 * The backend `/ws` endpoint authenticates by the `access_token` httpOnly cookie
 * (with a `?token=` query fallback). In dev the Vite proxy forwards `/ws` →
 * `ws://localhost:8000`; in production the FastAPI app serves the SPA from the
 * same origin, so the cookie flows and the path is identical. The browser
 * attaches the cookie on the WS handshake automatically — no JS-readable token
 * is needed, which is the whole point (httpOnly cookie auth finally reaches WS).
 *
 * Backend message shape (app/websocket/notifications.py):
 *   { type: "notification", payload: { event, title, message, resource, timestamp } }
 *
 * `AnalysisProgressResource` mirrors the `analysis.progress` event resource
 * written by `app/services/audit/analysis_service.py::_run_analysis_job`:
 *   { task_id, completed, total, new_findings, dimension_name }.
 *
 * Usage: `useAnalysisProgress(taskId, handler)` connects once per task and
 * dispatches `analysis.progress` events whose `resource.task_id` matches.
 */

/** analysis.progress event resource (mirrors backend notify_user resource). */
export interface AnalysisProgressResource {
  task_id: number
  completed: number
  total: number
  new_findings: number
  dimension_name?: string
}

/** Backend notification payload (app/websocket/notifications.py). */
export interface WsNotificationPayload {
  event: string
  title: string
  message: string
  resource: Record<string, unknown>
  timestamp: string
}

/** Backend WS envelope. */
export interface WsEnvelope {
  type: "notification"
  payload: WsNotificationPayload
}

/** Build the /ws URL for the current origin (dev proxy + prod same-origin). */
export function buildWsUrl(): string {
  if (typeof window === "undefined") return ""
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${proto}//${window.location.host}/ws`
}

/**
 * Connect an authenticated WebSocket and dispatch `analysis.progress` events
 * for a given task. Returns a controller with `close()` + a `healthy` flag the
 * caller can read to decide whether to fall back to polling.
 *
 * Reconnect: on unexpected close/error, retries once after a short delay. The
 * caller owns the lifecycle (close on unmount / task switch).
 */
export function openAnalysisProgressSocket(
  taskId: number,
  onProgress: (res: AnalysisProgressResource) => void,
): { close: () => void; healthy: () => boolean } {
  if (typeof window === "undefined") {
    return { close: () => {}, healthy: () => false }
  }

  let ws: WebSocket | null = null
  let closedByCaller = false
  let healthy = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    try {
      ws = new WebSocket(buildWsUrl())
    } catch {
      healthy = false
      return
    }

    ws.onopen = () => {
      healthy = true
    }

    ws.onmessage = (ev) => {
      let envelope: WsEnvelope | null = null
      try {
        envelope = JSON.parse(ev.data) as WsEnvelope
      } catch {
        return
      }
      if (!envelope || envelope.type !== "notification") return
      const payload = envelope.payload
      if (!payload || payload.event !== "analysis.progress") return
      const resource = payload.resource as Partial<AnalysisProgressResource> | undefined
      if (!resource || resource.task_id !== taskId) return
      onProgress({
        task_id: resource.task_id ?? taskId,
        completed: resource.completed ?? 0,
        total: resource.total ?? 0,
        new_findings: resource.new_findings ?? 0,
        dimension_name: resource.dimension_name,
      })
    }

    ws.onerror = () => {
      healthy = false
    }

    ws.onclose = () => {
      healthy = false
      ws = null
      // One reconnect attempt; the caller can fall back to polling if WS stays
      // down (RVP: WS primary, poll降级兜底).
      if (!closedByCaller && reconnectTimer == null) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null
          if (!closedByCaller) connect()
        }, 1500)
      }
    }
  }

  connect()

  return {
    close() {
      closedByCaller = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      if (ws) {
        ws.onclose = null
        ws.onerror = null
        ws.onmessage = null
        try {
          ws.close()
        } catch {
          // ignore
        }
        ws = null
      }
      healthy = false
    },
    healthy: () => healthy,
  }
}
