# -*- coding: utf-8 -*-
"""Notification helpers for WebSocket broadcasts."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.websocket.manager import manager

logger = logging.getLogger(__name__)


async def notify_user(
    user_id: int,
    event: str,
    title: str,
    message: str,
    resource: dict[str, Any] | None = None,
) -> None:
    """Broadcast a notification to a user without raising into callers."""
    payload = {
        "event": event,
        "title": title,
        "message": message,
        "resource": resource or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await manager.send_to_user(user_id, {"type": "notification", "payload": payload})
    except Exception as exc:
        logger.warning("Notification broadcast failed for user %s: %s", user_id, exc)
