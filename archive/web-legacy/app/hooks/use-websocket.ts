/**
 * WebSocket hook for React components
 */

import { useEffect, useCallback, useState } from "react";
import {
  getWebSocketManager,
  resetWebSocketManager,
  type WebSocketStatus,
  type WebSocketMessage,
} from "~/lib/websocket";
import { useAuth } from "./use-auth";

export function useWebSocket(path = "/ws") {
  const { isAuthenticated } = useAuth();
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      resetWebSocketManager();
      setStatus("disconnected");
      return;
    }

    const manager = getWebSocketManager({
      onMessage: (message) => {
        setLastMessage(message);
      },
      onStatusChange: (newStatus) => {
        setStatus(newStatus);
      },
    });

    manager.connect(path);

    return () => {
      resetWebSocketManager();
    };
  }, [isAuthenticated, path]);

  const send = useCallback((type: string, payload?: unknown) => {
    const manager = getWebSocketManager();
    manager.send({ type, payload });
  }, []);

  return {
    status,
    lastMessage,
    send,
    isConnected: status === "connected",
  };
}
