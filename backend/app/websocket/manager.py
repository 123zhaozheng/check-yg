# -*- coding: utf-8 -*-
"""WebSocket connection management."""

import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Track active WebSocket connections by user."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """Accept and register a user WebSocket connection."""
        await websocket.accept()
        self._connections.setdefault(user_id, set()).add(websocket)
        logger.info("WebSocket connected for user %s", user_id)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """Remove a user WebSocket connection."""
        connections = self._connections.get(user_id)
        if not connections:
            return

        connections.discard(websocket)
        if not connections:
            self._connections.pop(user_id, None)
        logger.info("WebSocket disconnected for user %s", user_id)

    async def send_to_user(self, user_id: int, message: dict[str, Any]) -> None:
        """Send a message to all active connections for a user."""
        connections = list(self._connections.get(user_id, set()))
        for websocket in connections:
            if websocket.client_state != WebSocketState.CONNECTED:
                self.disconnect(user_id, websocket)
                continue

            try:
                await websocket.send_json(message)
            except Exception as exc:
                logger.warning("WebSocket send failed for user %s: %s", user_id, exc)
                self.disconnect(user_id, websocket)

    def connection_count(self, user_id: int) -> int:
        """Return active connection count for tests and diagnostics."""
        return len(self._connections.get(user_id, set()))


manager = ConnectionManager()
