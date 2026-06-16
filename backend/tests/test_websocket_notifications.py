# -*- coding: utf-8 -*-
"""WebSocket notification tests."""

import pytest
from starlette.websockets import WebSocketState

from app.websocket.manager import ConnectionManager
from app.websocket.notifications import notify_user
from app.websocket.router import _authenticate_websocket


class DummyWebSocket:
    """Minimal WebSocket double for manager tests."""

    def __init__(self, fail_send=False):
        self.accepted = False
        self.client_state = WebSocketState.CONNECTED
        self.fail_send = fail_send
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.messages.append(message)


class DummyAuthWebSocket:
    """Minimal WebSocket double for auth tests."""

    def __init__(self, token=None):
        self.query_params = {}
        if token is not None:
            self.query_params["token"] = token


class DummyUser:
    id = 1
    is_active = True


class DummyScalarResult:
    def scalar_one_or_none(self):
        return DummyUser()


class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def execute(self, query):
        return DummyScalarResult()


@pytest.mark.asyncio
async def test_connection_manager_sends_to_all_user_connections():
    manager = ConnectionManager()
    first = DummyWebSocket()
    second = DummyWebSocket()

    await manager.connect(1, first)
    await manager.connect(1, second)
    await manager.send_to_user(1, {"type": "notification"})

    assert first.accepted
    assert second.accepted
    assert first.messages == [{"type": "notification"}]
    assert second.messages == [{"type": "notification"}]
    assert manager.connection_count(1) == 2


@pytest.mark.asyncio
async def test_connection_manager_drops_failed_connections():
    manager = ConnectionManager()
    failed = DummyWebSocket(fail_send=True)
    healthy = DummyWebSocket()

    await manager.connect(1, failed)
    await manager.connect(1, healthy)
    await manager.send_to_user(1, {"type": "notification"})

    assert healthy.messages == [{"type": "notification"}]
    assert manager.connection_count(1) == 1


@pytest.mark.asyncio
async def test_authenticate_websocket_rejects_missing_or_invalid_token(monkeypatch):
    monkeypatch.setattr("app.websocket.router.verify_token", lambda token: None)

    assert await _authenticate_websocket(DummyAuthWebSocket()) is None
    assert await _authenticate_websocket(DummyAuthWebSocket("bad-token")) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_loads_active_user(monkeypatch):
    monkeypatch.setattr(
        "app.websocket.router.verify_token",
        lambda token: {"type": "access", "sub": "1"},
    )
    monkeypatch.setattr("app.websocket.router.async_session", lambda: DummySession())

    user = await _authenticate_websocket(DummyAuthWebSocket("token"))

    assert user is not None
    assert user.id == 1


@pytest.mark.asyncio
async def test_notify_user_does_not_raise_when_broadcast_fails(monkeypatch):
    async def fail_send_to_user(user_id, message):
        raise RuntimeError("broadcast failed")

    monkeypatch.setattr("app.websocket.notifications.manager.send_to_user", fail_send_to_user)

    await notify_user(
        1,
        event="review.completed",
        title="done",
        message="review done",
        resource={"review_id": 1},
    )
