# -*- coding: utf-8 -*-
"""Backend test fixtures."""

import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.main import app
from app.models import Role, User
from app.models.base import Base


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        role = Role(name="auditor")
        user = User(
            username="owner",
            email="owner@example.com",
            hashed_password="x",
            role=role,
            is_active=True,
        )
        session.add_all([role, user])
        await session.commit()
        await session.refresh(user)
        yield session, user

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    session, user = db_session

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def temp_output_dir(monkeypatch):
    import shutil

    output_dir = Path.cwd() / "data" / "test_outputs"
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.OUTPUT_DIR", os.path.join(output_dir))
    yield output_dir
    shutil.rmtree(output_dir, ignore_errors=True)
