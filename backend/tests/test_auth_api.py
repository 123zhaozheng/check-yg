# -*- coding: utf-8 -*-
"""Authentication API contract tests."""

from datetime import timedelta

import pytest

from app.auth.jwt import create_access_token, create_refresh_token
from app.auth.dependencies import get_current_user
from app.auth.password import hash_password
from app.database import get_db
from app.main import app
from app.models import Role, User


@pytest.mark.asyncio
async def test_login_returns_access_and_refresh_tokens(client, db_session):
    session, _user = db_session
    role = Role(name="login-role")
    user = User(
        username="login-user",
        email="login@example.com",
        hashed_password=hash_password("secret"),
        role=role,
        is_active=True,
    )
    session.add_all([role, user])
    await session.commit()

    response = await client.post(
        "/api/auth/login",
        json={"username": "login-user", "password": "secret"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(client, db_session):
    _session, user = db_session
    access_token = create_access_token(user.id)

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": access_token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_tokens(client, db_session):
    _session, user = db_session
    refresh_token = create_refresh_token(user.id)

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_me_rejects_refresh_token(client, db_session):
    session, user = db_session
    refresh_token = create_refresh_token(user.id)

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db] = _override_db(session)
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer %s" % refresh_token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_access_token_is_rejected(client, db_session):
    session, user = db_session
    access_token = create_access_token(user.id, expires_delta=timedelta(seconds=-1))

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db] = _override_db(session)
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer %s" % access_token},
    )

    assert response.status_code == 401


def _override_db(session):
    async def override():
        yield session

    return override


# ---------------------------------------------------------------------------
# Cookie auth closed loop (B1 块2): login Set-Cookie -> me reads cookie ->
# refresh reads cookie -> logout clears cookie.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_sets_httponly_cookies(client, db_session):
    session, _user = db_session
    role = Role(name="cookie-role")
    user = User(
        username="cookie-user",
        email="cookie@example.com",
        hashed_password=hash_password("secret"),
        role=role,
        is_active=True,
    )
    session.add_all([role, user])
    await session.commit()

    response = await client.post(
        "/api/auth/login",
        json={"username": "cookie-user", "password": "secret"},
    )

    assert response.status_code == 200
    set_cookies = response.headers.get_list("set-cookie")
    cookie_keys = [c.split("=", 1)[0] for c in set_cookies]
    assert "access_token" in cookie_keys
    assert "refresh_token" in cookie_keys
    # httponly + samesite=strict 必须出现
    joined = "; ".join(set_cookies).lower()
    assert "httponly" in joined
    assert "samesite=strict" in joined


@pytest.mark.asyncio
async def test_me_reads_access_token_from_cookie(client, db_session):
    session, user = db_session
    access_token = create_access_token(user.id)

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db] = _override_db(session)
    response = await client.get(
        "/api/auth/me",
        cookies={"access_token": access_token},
    )

    assert response.status_code == 200
    assert response.json()["username"] == user.username


@pytest.mark.asyncio
async def test_refresh_reads_refresh_token_from_cookie(client, db_session):
    _session, user = db_session
    refresh_token = create_refresh_token(user.id)

    response = await client.post(
        "/api/auth/refresh",
        cookies={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    set_cookies = response.headers.get_list("set-cookie")
    cookie_keys = [c.split("=", 1)[0] for c in set_cookies]
    assert "access_token" in cookie_keys  # 新 access cookie 下发


@pytest.mark.asyncio
async def test_refresh_without_token_is_rejected(client, db_session):
    response = await client.post("/api/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_cookies(client, db_session):
    response = await client.post("/api/auth/logout")

    assert response.status_code == 200
    set_cookies = response.headers.get_list("set-cookie")
    # delete_cookie 通过 set max-age=0 / expires 过期
    joined = "; ".join(set_cookies).lower()
    assert "access_token=" in joined
    assert "refresh_token=" in joined
    assert "max-age=0" in joined or "expires=" in joined
