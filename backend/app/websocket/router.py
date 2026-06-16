# -*- coding: utf-8 -*-
"""Authenticated WebSocket router."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.auth.jwt import verify_token
from app.database import async_session
from app.models import User
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept authenticated WebSocket connections."""
    user = await _authenticate_websocket(websocket)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
    except Exception as exc:
        logger.warning("WebSocket connection failed for user %s: %s", user.id, exc)
        manager.disconnect(user.id, websocket)


async def _authenticate_websocket(websocket: WebSocket) -> User | None:
    token = websocket.query_params.get("token")
    if not token:
        return None

    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        async with async_session() as db:
            result = await db.execute(select(User).where(User.id == int(user_id)))
            user = result.scalar_one_or_none()
    except (TypeError, ValueError) as exc:
        logger.warning("Invalid WebSocket token subject: %s", exc)
        return None

    if not user or not user.is_active:
        return None
    return user
