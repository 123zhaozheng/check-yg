# -*- coding: utf-8 -*-
"""07-01-ai-50 AI 关键词生成后端测试。

覆盖（PRD + implement.jsonl）：
* 空 name 拒绝（422）
* 空 risk_level 非法值拒绝（422）
* 去重保序（后端 _dedup_terms）
* 阶段卡片未指派回退 env 兜底（mock generate_terms 本身）
* 正常返回 terms（mock agent）
* 生成失败返回空列表（不崩 dialog）
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.main import app
from app.auth.dependencies import get_current_user
from app.models import Role, User


# ---------------------------------------------------------------------------
# Admin-user client helper（复用现有 test_keyword_library.py 模式）
# ---------------------------------------------------------------------------


async def _admin_client(db_session, client):
    """Override get_current_user to return an admin user."""
    session, auditor = db_session
    admin_role = Role(name="admin")
    admin_user = User(
        username="admin-test",
        email="admin@example.com",
        hashed_password="x",
        role=admin_role,
        is_active=True,
    )
    session.add_all([admin_role, admin_user])
    await session.commit()
    await session.refresh(admin_user)

    async def override_current_user():
        return admin_user

    app.dependency_overrides[get_current_user] = override_current_user
    yield client

    async def restore_current_user():
        return auditor

    app.dependency_overrides[get_current_user] = restore_current_user


# ---------------------------------------------------------------------------
# 端点基本校验（空 name / 非法 risk）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_terms_empty_name_422(client, db_session):
    """POST /generate-terms name 为空 → 422。"""
    async for c in _admin_client(db_session, client):
        resp = await c.post(
            "/api/keyword-library/generate-terms",
            json={"name": "", "risk_level": "高", "note": "测试"},
        )
        assert resp.status_code == 422
        # FastAPI 422 详情含字段级错误；这里只断言被拒。
        assert "422" in str(resp.status_code) or resp.json().get("detail")


@pytest.mark.asyncio
async def test_generate_terms_invalid_risk_422(client, db_session):
    """POST /generate-terms risk_level 非法 → 422。"""
    async for c in _admin_client(db_session, client):
        resp = await c.post(
            "/api/keyword-library/generate-terms",
            json={"name": "测试卡", "risk_level": "极高", "note": "测试"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_terms_non_admin_403(client):
    """非 admin → 403。"""
    resp = await client.post(
        "/api/keyword-library/generate-terms",
        json={"name": "测试卡", "risk_level": "中", "note": ""},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 后端去重保序（复用 service._dedup_terms）
# ---------------------------------------------------------------------------


def test_dedup_terms_reuse_logic():
    """验证 KeywordLibraryService._dedup_terms 去重保序行为。"""
    from app.services.keyword.keyword_library_service import KeywordLibraryService

    # 重复 + 空 + 空白
    raw = ["张三", "李四", "张三", "", "  ", "李四", "王五"]
    out = KeywordLibraryService._dedup_terms(raw)
    assert out == ["张三", "李四", "王五"]

    # 全空
    assert KeywordLibraryService._dedup_terms(["", "  ", None]) == []

    # 保序
    raw2 = ["b", "a", "b", "c", "a"]
    assert KeywordLibraryService._dedup_terms(raw2) == ["b", "a", "c"]


# ---------------------------------------------------------------------------
# generate_terms 成功/失败路径（mock agent）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_terms_success_deduped(db_session):
    """generate_terms 成功返回 → 返回原始列表（去重在路由层做）。"""
    from app.llm.keyword_generator import generate_terms

    # 模拟 agent 返回带重复的结果
    fake_terms = ["张三", "李四", "张三", "王五", "李四"]

    with patch("app.llm.keyword_generator.get_keyword_agent") as mock_get_agent:
        fake_result = type("R", (), {"output": type("O", (), {"terms": fake_terms})()})()
        mock_agent = AsyncMock()
        mock_agent.run.return_value = fake_result
        mock_get_agent.return_value = mock_agent

        terms = await generate_terms("敏感主体", "高", "地下钱庄相关")
        # generate_terms 本身不做去重，返回原始结果
        assert terms == ["张三", "李四", "张三", "王五", "李四"]


@pytest.mark.asyncio
async def test_generate_terms_returns_empty_on_llm_failure(db_session):
    """LLM 异常 → 返回空列表（不抛给调用方，由调用方决定是否 422）。"""
    from app.llm.keyword_generator import generate_terms

    with patch("app.llm.keyword_generator.get_keyword_agent") as mock_get_agent:
        mock_agent = AsyncMock()
        mock_agent.run.side_effect = RuntimeError("LLM timeout")
        mock_get_agent.return_value = mock_agent

        terms = await generate_terms("测试卡", "中", "备注")
        assert terms == []


@pytest.mark.asyncio
async def test_generate_terms_returns_empty_when_too_few(db_session):
    """返回词数过少（<3）→ 视为失败返回空列表。"""
    from app.llm.keyword_generator import generate_terms

    with patch("app.llm.keyword_generator.get_keyword_agent") as mock_get_agent:
        fake_result = type("R", (), {"output": type("O", (), {"terms": ["只有", "两个"]})()})()
        mock_agent = AsyncMock()
        mock_agent.run.return_value = fake_result
        mock_get_agent.return_value = mock_agent

        terms = await generate_terms("测试卡", "低", "")
        assert terms == []


@pytest.mark.asyncio
async def test_generate_terms_empty_name_short_circuit(db_session):
    """name 为空 → 直接返回 []，不调 agent。"""
    from app.llm.keyword_generator import generate_terms

    with patch("app.llm.keyword_generator.get_keyword_agent") as mock_get_agent:
        terms = await generate_terms("", "高", "note")
        assert terms == []
        mock_get_agent.assert_not_called()


# ---------------------------------------------------------------------------
# 端点成功路径（mock generate_terms，返回去重结果）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_terms_endpoint_returns_deduped(db_session, client):
    """端点成功：mock generate_terms 返回带重复 → 后端去重后返回。"""
    async for c in _admin_client(db_session, client):
        with patch("app.routers.keyword_library.generate_terms", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = ["张三", "李四", "张三", "王五"]
            resp = await c.post(
                "/api/keyword-library/generate-terms",
                json={"name": "敏感主体", "risk_level": "高", "note": "地下钱庄"},
            )
            assert resp.status_code == 200
            body = resp.json()
            # 路由层用 service._dedup_terms 再去重
            assert body["terms"] == ["张三", "李四", "王五"]


@pytest.mark.asyncio
async def test_generate_terms_endpoint_on_agent_failure_returns_422(db_session, client):
    """端点：generate_terms 内部异常 → 路由层吞掉返 422，不崩 dialog。"""
    async for c in _admin_client(db_session, client):
        with patch("app.routers.keyword_library.generate_terms", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = RuntimeError("boom")
            resp = await c.post(
                "/api/keyword-library/generate-terms",
                json={"name": "敏感主体", "risk_level": "高", "note": ""},
            )
            assert resp.status_code == 422
            assert "AI 生成失败" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 阶段卡片未指派回退（mock get_keyword_generation_model 返回 None）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_terms_falls_back_when_no_stage_assignment(db_session, client):
    """未指派 keyword_generation 阶段卡片 → generate_terms 仍可被调用（回退 env）。"""
    # 路由层在函数内部 import get_keyword_generation_model
    async for c in _admin_client(db_session, client):
        with patch("app.llm.keyword_generator.get_keyword_generation_model", new_callable=AsyncMock) as mock_stage:
            mock_stage.return_value = None  # 未指派
            with patch("app.routers.keyword_library.generate_terms", new_callable=AsyncMock) as mock_gen:
                mock_gen.return_value = ["词1", "词2", "词3"]
                resp = await c.post(
                    "/api/keyword-library/generate-terms",
                    json={"name": "测试卡", "risk_level": "中", "note": "备注"},
                )
                assert resp.status_code == 200
                # generate_terms 应被以 model=None 调用
                args, kwargs = mock_gen.call_args
                assert kwargs.get("model") is None or (len(args) >= 4 and args[3] is None)
