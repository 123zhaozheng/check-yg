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
    # 鉴权兼容两条路径（PRD §十一 WS 逐条推进度需要前端能连）：
    # 1. query-param ``token``（保留，向后兼容现有客户端/测试）。
    # 2. ``access_token`` httpOnly cookie（前端 JS 读不到 cookie，但浏览器 WS
    #    握手会自动带同源 cookie —— 这是 SPA 走 WS 的唯一可行路径）。
    # 两者任一有效即通过，都无效才拒。
    token = websocket.query_params.get("token")
    if not token:
        cookies = getattr(websocket, "cookies", None) or {}
        token = cookies.get("access_token")
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
