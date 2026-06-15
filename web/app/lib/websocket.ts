/**
 * WebSocket connection manager with reconnection logic
 */

import { getToken } from "./api";

const WS_BASE = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

export interface WebSocketMessage {
  type: string;
  payload?: unknown;
}

export interface WebSocketManagerOptions {
  onMessage?: (message: WebSocketMessage) => void;
  onStatusChange?: (status: WebSocketStatus) => void;
  reconnectAttempts?: number;
  reconnectDelay?: number;
}

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectCount = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private options: Required<WebSocketManagerOptions>;

  constructor(options: WebSocketManagerOptions = {}) {
    this.options = {
      onMessage: options.onMessage || (() => {}),
      onStatusChange: options.onStatusChange || (() => {}),
      reconnectAttempts: options.reconnectAttempts ?? 5,
      reconnectDelay: options.reconnectDelay ?? 3000,
    };
  }

  connect(path = "/ws"): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.setStatus("connecting");

    const token = getToken();
    const wsUrl = token ? `${WS_BASE}${path}?token=${token}` : `${WS_BASE}${path}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.reconnectCount = 0;
        this.setStatus("connected");
      };

      this.ws.onclose = () => {
        this.setStatus("disconnected");
        this.attemptReconnect(path);
      };

      this.ws.onerror = () => {
        this.setStatus("error");
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage;
          this.options.onMessage(message);
        } catch {
          // Ignore non-JSON messages
        }
      };
    } catch {
      this.setStatus("error");
      this.attemptReconnect(path);
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectCount = this.options.reconnectAttempts; // Prevent reconnect
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setStatus("disconnected");
  }

  send(message: WebSocketMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  private attemptReconnect(path: string): void {
    if (this.reconnectCount >= this.options.reconnectAttempts) {
      return;
    }

    this.reconnectCount++;
    this.reconnectTimer = setTimeout(() => {
      this.connect(path);
    }, this.options.reconnectDelay);
  }

  private setStatus(status: WebSocketStatus): void {
    this.options.onStatusChange(status);
  }
}

// Singleton instance
let wsManager: WebSocketManager | null = null;

export function getWebSocketManager(options?: WebSocketManagerOptions): WebSocketManager {
  if (!wsManager) {
    wsManager = new WebSocketManager(options);
  }
  return wsManager;
}

export function resetWebSocketManager(): void {
  if (wsManager) {
    wsManager.disconnect();
    wsManager = null;
  }
}
