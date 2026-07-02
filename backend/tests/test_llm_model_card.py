# -*- coding: utf-8 -*-
"""06-23-llm-model-card tests: 模型卡片 + 阶段指派 + 三模块接线 + seed + admin 鉴权.

Covers (per prd §⑥):
* 模型卡片 CRUD（5）：create / list-api_key 脱敏 / update-留空不改 api_key /
  update-新 api_key / delete。
* 阶段指派 GET/PUT（2）：list 6 阶段 / put 指派+解除。
* 三模块按阶段从卡片读 max_tokens/thinking 接线（3）：portrait 指派 reasoning
  卡片 → max_tokens/thinking 来自卡片；未指派 → 回退兜底；classifier/normalizer
  同理。
* seed 默认卡片+assignments（1）：seed 幂等插入 4 张卡片，assignments 留空。
* admin 鉴权拒绝 auditor 改（1）：非 admin 调 POST/PUT/DELETE/指派 → 403。

Mock LLM agent + sqlite 内存 DB — no real network.
"""

import pytest
from sqlalchemy import select

from app.auth.dependencies import get_current_user
from app.main import app
from app.models import LLMModel, LLMModelAssignment, Role, User
from app.models.llm_model import THINKING_OFF
from app.models.llm_model_assignment import (
    STAGE_CLASSIFICATION,
    STAGE_NORMALIZATION,
    STAGE_PORTRAIT,
)
from app.services.extraction.extractor import FlowExtractor
from app.services.llm_model_service import (
    get_stage_model,
    load_stage_models,
    seed_default_llm_models,
)


# ---------------------------------------------------------------------------
# Admin-user client helper（admin 鉴权测试需要 admin 角色）
# ---------------------------------------------------------------------------


async def _admin_client(db_session, client):
    """Override get_current_user to return an admin user for the duration of the block.

    Usage::

        async for c in _admin_client(db_session, client):
            resp = await c.post(...)

    On exit the override is restored to the default auditor user so subsequent
    tests get the standard non-admin client.
    """
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
# 模型卡片 CRUD（5）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_llm_model_admin(db_session, client):
    """POST /api/llm-models (admin) creates a card; api_key stored, response masked."""
    async for c in _admin_client(db_session, client):
        resp = await c.post(
            "/api/llm-models",
            json={
                "display_name": "kimi-2.7",
                "model_name": "kimi-k2.7",
                "provider_base_url": "https://api.moonshot.ai/v1",
                "api_key": "sk-secret-1234",
                "context_length": 262144,
                "max_output": 32768,
                "supports_tool_call": True,
                "supports_tool_choice_required": True,
                "is_reasoning": True,
                "supports_streaming": True,
                "default_thinking": "low",
                "default_max_tokens": 6000,
                "default_temperature": None,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["display_name"] == "kimi-2.7"
        # api_key 脱敏：返 ********1234，不返明文。
        assert body["api_key"] == "********1234"
        assert "sk-secret" not in resp.text


@pytest.mark.asyncio
async def test_list_llm_models_api_key_masked(db_session, client):
    """GET /api/llm-models returns api_key masked for all login users."""
    session, _user = db_session
    session.add(
        LLMModel(
            display_name="card1",
            model_name="m1",
            provider_base_url="https://x/v1",
            api_key="sk-abcdef9999",
            context_length=8000,
            max_output=4000,
            default_max_tokens=4000,
        )
    )
    await session.commit()

    resp = await client.get("/api/llm-models")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["api_key"] == "********9999"
    assert "sk-abcdef" not in resp.text


@pytest.mark.asyncio
async def test_update_llm_model_blank_api_key_keeps_original(db_session, client):
    """PUT /api/llm-models/{id} with blank/masked api_key keeps the original value."""
    session, _user = db_session
    model = LLMModel(
        display_name="card-keep",
        model_name="m-keep",
        provider_base_url="https://x/v1",
        api_key="sk-orig-AAAA",
        context_length=8000,
        max_output=4000,
        default_max_tokens=4000,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    original_key = model.api_key
    mid = model.id

    async for c in _admin_client(db_session, client):
        # 留空（None → JSON null/省略）不改原值。
        resp = await c.put(
            f"/api/llm-models/{mid}",
            json={"display_name": "card-keep-renamed"},
        )
        assert resp.status_code == 200, resp.text
        # 脱敏占位串也不改原值。
        resp2 = await c.put(
            f"/api/llm-models/{mid}",
            json={"api_key": "********AAAA"},
        )
        assert resp2.status_code == 200

    await session.refresh(model)
    assert model.api_key == original_key
    assert model.display_name == "card-keep-renamed"


@pytest.mark.asyncio
async def test_update_llm_model_new_api_key_overwrites(db_session, client):
    """PUT /api/llm-models/{id} with a fresh (non-masked) api_key overwrites."""
    session, _user = db_session
    model = LLMModel(
        display_name="card-overw",
        model_name="m-overw",
        provider_base_url="https://x/v1",
        api_key="sk-old-XXXX",
        context_length=8000,
        max_output=4000,
        default_max_tokens=4000,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    mid = model.id

    async for c in _admin_client(db_session, client):
        resp = await c.put(
            f"/api/llm-models/{mid}",
            json={"api_key": "sk-new-YYYY"},
        )
        assert resp.status_code == 200, resp.text

    await session.refresh(model)
    assert model.api_key == "sk-new-YYYY"


@pytest.mark.asyncio
async def test_delete_llm_model_assigned_rejected_409(db_session, client):
    """DELETE a card that's assigned to a stage → 409; unassigned → 204."""
    session, _user = db_session
    model = LLMModel(
        display_name="card-del",
        model_name="m-del",
        provider_base_url="https://x/v1",
        api_key="",
        context_length=8000,
        max_output=4000,
        default_max_tokens=4000,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    mid = model.id

    # Assign it to portrait stage first.
    session.add(LLMModelAssignment(stage=STAGE_PORTRAIT, llm_model_id=mid))
    await session.commit()

    async for c in _admin_client(db_session, client):
        resp = await c.delete(f"/api/llm-models/{mid}")
        assert resp.status_code == 409
        assert "指派" in resp.json()["detail"]

        # Unassign → delete succeeds.
        unassign = await c.put(
            f"/api/llm-model-assignments/{STAGE_PORTRAIT}",
            json={"llm_model_id": None},
        )
        assert unassign.status_code == 200
        resp2 = await c.delete(f"/api/llm-models/{mid}")
        assert resp2.status_code == 204

    gone = (
        await session.execute(select(LLMModel).where(LLMModel.id == mid))
    ).scalar_one_or_none()
    assert gone is None


@pytest.mark.asyncio
async def test_delete_llm_model_force_unassigns_then_deletes(db_session, client):
    """DELETE ?force=true on an assigned card → unassigns all referencing stages
    then deletes (204); the assignment rows remain with llm_model_id=None."""
    session, _user = db_session
    model = LLMModel(
        display_name="card-force",
        model_name="m-force",
        provider_base_url="https://x/v1",
        api_key="",
        context_length=8000,
        max_output=4000,
        default_max_tokens=4000,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    mid = model.id

    # Assign to two stages.
    session.add(LLMModelAssignment(stage=STAGE_PORTRAIT, llm_model_id=mid))
    session.add(LLMModelAssignment(stage=STAGE_CLASSIFICATION, llm_model_id=mid))
    await session.commit()

    async for c in _admin_client(db_session, client):
        # Default (no force) → still 409.
        resp = await c.delete(f"/api/llm-models/{mid}")
        assert resp.status_code == 409

        # force=true → 204, unassigns first.
        resp2 = await c.delete(f"/api/llm-models/{mid}?force=true")
        assert resp2.status_code == 204

    # Card gone.
    gone = (
        await session.execute(select(LLMModel).where(LLMModel.id == mid))
    ).scalar_one_or_none()
    assert gone is None

    # Assignment rows remain but llm_model_id nulled.
    assigns = (
        await session.execute(
            select(LLMModelAssignment).where(
                LLMModelAssignment.stage.in_([STAGE_PORTRAIT, STAGE_CLASSIFICATION])
            )
        )
    ).scalars().all()
    assert len(assigns) == 2
    assert all(a.llm_model_id is None for a in assigns)


# ---------------------------------------------------------------------------
# 阶段指派 GET/PUT（2）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_assignments_returns_all_six_stages(db_session, client):
    """GET /api/llm-model-assignments returns all 6 stages (unassigned = None)."""
    resp = await client.get("/api/llm-model-assignments")
    assert resp.status_code == 200
    items = resp.json()
    stages = {item["stage"] for item in items}
    assert stages == {
        "classification",
        "portrait",
        "normalization",
        "ai_analysis",
        "ai_qa",
        "report_generation",
    }
    # All unassigned by default.
    for item in items:
        assert item["llm_model"] is None
        assert item["llm_model_id"] is None


@pytest.mark.asyncio
async def test_put_assignment_assigns_and_unassigns(db_session, client):
    """PUT /api/llm-model-assignments/{stage} assigns a card, then null unassigns."""
    session, _user = db_session
    model = LLMModel(
        display_name="card-assign",
        model_name="m-assign",
        provider_base_url="https://x/v1",
        api_key="sk-secret-7777",
        context_length=8000,
        max_output=4000,
        default_max_tokens=6000,
        is_reasoning=True,
        default_thinking="low",
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    mid = model.id

    async for c in _admin_client(db_session, client):
        resp = await c.put(
            f"/api/llm-model-assignments/{STAGE_PORTRAIT}",
            json={"llm_model_id": mid},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["llm_model_id"] == mid
        assert body["llm_model"]["display_name"] == "card-assign"
        # api_key masked in assignment response too.
        assert body["llm_model"]["api_key"] == "********7777"

        # Unassign.
        resp2 = await c.put(
            f"/api/llm-model-assignments/{STAGE_PORTRAIT}",
            json={"llm_model_id": None},
        )
        assert resp2.status_code == 200
        assert resp2.json()["llm_model_id"] is None
        assert resp2.json()["llm_model"] is None

        # Invalid stage → 422.
        resp3 = await c.put(
            "/api/llm-model-assignments/bogus",
            json={"llm_model_id": None},
        )
        assert resp3.status_code == 422

        # Nonexistent model id → 404.
        resp4 = await c.put(
            f"/api/llm-model-assignments/{STAGE_PORTRAIT}",
            json={"llm_model_id": 99999},
        )
        assert resp4.status_code == 404


# ---------------------------------------------------------------------------
# 三模块按阶段从卡片读 max_tokens/thinking 接线（3）
# ---------------------------------------------------------------------------


def _make_reasoning_card() -> LLMModel:
    """A step-3.7-flash-like reasoning card (default_max_tokens=6000, thinking=low)."""
    return LLMModel(
        id=1,
        display_name="step-3.7-flash",
        model_name="step-3.7-flash",
        provider_base_url="https://api.stepfun.com/v1",
        api_key="sk-card",
        context_length=262144,
        max_output=8192,
        supports_tool_call=True,
        supports_tool_choice_required=True,
        is_reasoning=True,
        supports_streaming=True,
        default_thinking="low",
        default_max_tokens=6000,
        default_temperature=None,
    )


def test_extractor_portrait_uses_card_max_tokens_and_thinking():
    """Portrait stage assigned a reasoning card → max_tokens/thinking come from the card."""
    card = _make_reasoning_card()
    extractor = FlowExtractor(
        runtime_settings={},
        stage_models={STAGE_PORTRAIT: card},
    )
    portrait = extractor.portrait_extractor
    assert portrait.max_tokens == 6000
    assert portrait.thinking == "low"
    assert portrait.api_url == "https://api.stepfun.com/v1"
    assert portrait.model == "step-3.7-flash"
    # Classifier/normalizer unassigned → fall back to module constants (runtime empty).
    assert extractor.classifier.max_tokens != 6000
    assert extractor.normalizer.max_tokens != 6000


def test_extractor_unassigned_falls_back_to_module_constant():
    """Unassigned stage → module hardcoded constants (runtime llm.* 中间兜底层
    已于 06-23-tab 去除：extractor 不再读 runtime llm.max_tokens 作 fallback)。"""
    # runtime llm.max_tokens=12000 现在被忽略（中间兜底层已删）→ 用模块常量。
    extractor = FlowExtractor(
        runtime_settings={"llm.max_tokens": "12000"},
        stage_models={},
    )
    from app.llm.classifier import _MAX_TOKENS_CLASSIFIER
    from app.llm.normalizer import _MAX_TOKENS_NORMALIZER
    from app.llm.portrait import _MAX_TOKENS_PORTRAIT

    assert extractor.classifier.max_tokens == _MAX_TOKENS_CLASSIFIER
    assert extractor.portrait_extractor.max_tokens == _MAX_TOKENS_PORTRAIT
    assert extractor.normalizer.max_tokens == _MAX_TOKENS_NORMALIZER
    # No thinking when unassigned.
    assert extractor.portrait_extractor.thinking is None

    # runtime empty → 同样模块硬编码常量。
    extractor2 = FlowExtractor(runtime_settings={}, stage_models={})

    assert extractor2.classifier.max_tokens == _MAX_TOKENS_CLASSIFIER
    assert extractor2.portrait_extractor.max_tokens == _MAX_TOKENS_PORTRAIT
    assert extractor2.normalizer.max_tokens == _MAX_TOKENS_NORMALIZER


def test_extractor_non_reasoning_card_no_thinking():
    """A non-reasoning card (is_reasoning=False / thinking=off) → thinking=None."""
    card = LLMModel(
        id=2,
        display_name="deepseek-chat",
        model_name="deepseek-chat",
        provider_base_url="https://api.deepseek.com/v1",
        api_key="sk-card",
        context_length=1000000,
        max_output=384000,
        is_reasoning=False,
        default_thinking=THINKING_OFF,
        default_max_tokens=4000,
    )
    extractor = FlowExtractor(
        runtime_settings={},
        stage_models={STAGE_CLASSIFICATION: card},
    )
    # Non-reasoning card → thinking suppressed (no reasoning_effort sent).
    assert extractor.classifier.thinking is None
    assert extractor.classifier.max_tokens == 4000


def test_extractor_normalizer_supports_tool_choice_required_from_card():
    """A normalization-stage card declaring ``supports_tool_choice_required=False``
    (e.g. deepseek-v4-flash under thinking mode) → the flag reaches
    ``extractor.normalizer.supports_tool_choice_required`` as False; unassigned
    stages and True-declaring cards stay True (default behaviour).

    Regression for the DeepSeek 400 ``Thinking mode does not support this
    tool_choice`` failure: extractor must thread the card's flag into the
    three modules so ``agent_factory.get_agent`` can downgrade
    ``tool_choice=required`` to ``auto``.
    """
    false_card = LLMModel(
        id=3,
        display_name="deepseek-v4-flash",
        model_name="deepseek-v4-flash",
        provider_base_url="https://api.deepseek.com/v1",
        api_key="sk-card",
        context_length=131072,
        max_output=8192,
        supports_tool_call=True,
        supports_tool_choice_required=False,
        is_reasoning=True,
        default_thinking="low",
        default_max_tokens=6000,
        default_temperature=None,
    )
    extractor = FlowExtractor(
        runtime_settings={},
        stage_models={STAGE_NORMALIZATION: false_card},
    )
    # Card declares False → normalizer carries False.
    assert extractor.normalizer.supports_tool_choice_required is False
    # Other modules unassigned → default True.
    assert extractor.classifier.supports_tool_choice_required is True
    assert extractor.portrait_extractor.supports_tool_choice_required is True

    # A True-declaring card keeps True.
    true_card = _make_reasoning_card()  # supports_tool_choice_required=True
    extractor2 = FlowExtractor(
        runtime_settings={},
        stage_models={STAGE_NORMALIZATION: true_card},
    )
    assert extractor2.normalizer.supports_tool_choice_required is True

    # Unassigned (no card) also defaults to True.
    extractor3 = FlowExtractor(runtime_settings={}, stage_models={})
    assert extractor3.normalizer.supports_tool_choice_required is True


@pytest.mark.asyncio
async def test_reasoning_card_thinking_reaches_endpoint_as_reasoning_effort(monkeypatch):
    """Regression: a reasoning card's ``thinking=low`` must actually be delivered to
    the OpenAI-compatible endpoint as ``reasoning_effort=low``, not silently dropped.

    The default ``OpenAIChatModel`` profile has ``supports_thinking=False``; without
    passing ``OpenAIModelProfile(supports_thinking=True)`` for a reasoning model,
    ``Model.prepare_request`` strips ``thinking`` from model_settings and
    ``_translate_thinking`` returns OMIT → ``reasoning_effort`` is never sent. This
    test mocks the OpenAI client and inspects the actual ``chat.completions.create``
    kwargs so the bug can't hide behind a Python-attribute-only assertion.
    """
    from unittest.mock import MagicMock, patch

    from openai import Omit

    from app.llm.agent_factory import _agent_cache, get_agent
    from app.llm.types import DocumentPortrait

    # Isolated cache so this test's agent doesn't collide with others.
    _agent_cache.clear()

    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            msg = MagicMock(tool_calls=None, content="{}")
            choice = MagicMock(message=msg, finish_reason="stop")
            usage = MagicMock(prompt_tokens=1, completion_tokens=1)
            return MagicMock(choices=[choice], usage=usage)

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            self.chat = MagicMock(completions=FakeCompletions())

    card = _make_reasoning_card()  # step-3.7-flash, is_reasoning=True, thinking=low
    extractor = FlowExtractor(
        runtime_settings={},
        stage_models={STAGE_PORTRAIT: card},
    )

    with patch("openai.AsyncOpenAI", FakeAsyncOpenAI):
        portrait = extractor.portrait_extractor
        # Force a fresh agent build with the card's thinking=low.
        try:
            await portrait.extract("doc.pdf", "ctx", "preview")
        except Exception:
            # Output parsing fails on the mock's '{}' content — that's fine;
            # we only care the request was issued with reasoning_effort.
            pass

    assert "reasoning_effort" in captured, captured.keys()
    assert captured["reasoning_effort"] == "low"
    assert captured["max_completion_tokens"] == 6000
    # Non-reasoning sentinel must NOT leak as reasoning_effort value.
    assert not isinstance(captured["reasoning_effort"], Omit)

    # Non-reasoning card → reasoning_effort must NOT be sent (OMIT).
    _agent_cache.clear()
    captured.clear()
    non_reasoning = LLMModel(
        id=2,
        display_name="deepseek-chat",
        model_name="deepseek-chat",
        provider_base_url="https://api.deepseek.com/v1",
        api_key="sk-card",
        context_length=1000000,
        max_output=384000,
        is_reasoning=False,
        default_thinking=THINKING_OFF,
        default_max_tokens=4000,
    )
    extractor2 = FlowExtractor(
        runtime_settings={},
        stage_models={STAGE_PORTRAIT: non_reasoning},
    )
    with patch("openai.AsyncOpenAI", FakeAsyncOpenAI):
        try:
            await extractor2.portrait_extractor.extract("doc.pdf", "ctx", "preview")
        except Exception:
            pass
    assert isinstance(captured.get("reasoning_effort", Omit()), Omit), (
        "non-reasoning card must not send reasoning_effort"
    )


def test_agent_factory_configures_openai_http_retries():
    """OpenAI HTTP client retries transient 429/5xx failures five times."""
    from app.llm.agent_factory import _agent_cache, get_agent
    from app.llm.types import DocumentPortrait

    _agent_cache.clear()
    captured: dict = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("openai.AsyncOpenAI", FakeAsyncOpenAI):
        get_agent(
            DocumentPortrait,
            "instructions",
            base_url="https://llm.example.test/v1",
            api_key="sk-test",
            model="test-model",
            timeout=30,
            max_tokens=1000,
        )

    assert captured["max_retries"] == 5


@pytest.mark.asyncio
async def test_seed_default_llm_models_idempotent_assignments_empty(db_session):
    """seed_default_llm_models inserts 4 cards idempotently; assignments stay empty."""
    session, _user = db_session
    inserted = await seed_default_llm_models(session)
    assert len(inserted) == 4
    names = {m.display_name for m in inserted}
    assert names == {"step-3.7-flash", "deepseek-chat", "qwen-plus", "kimi-k2.6"}

    # Idempotent: second call inserts nothing.
    inserted2 = await seed_default_llm_models(session)
    assert inserted2 == []

    # Assignments empty (grill decision: user picks per-stage in the UI).
    assignments = (
        await session.execute(select(LLMModelAssignment))
    ).scalars().all()
    assert assignments == []

    # step-3.7-flash card seeded with reasoning defaults.
    step_model = (
        await session.execute(
            select(LLMModel).where(LLMModel.display_name == "step-3.7-flash")
        )
    ).scalar_one()
    assert step_model.is_reasoning is True
    assert step_model.default_thinking == "low"
    assert step_model.default_max_tokens == 6000


# ---------------------------------------------------------------------------
# admin 鉴权拒绝 auditor 改（1）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_rejected_from_crud_and_assignments(client):
    """Non-admin (auditor) user → POST/PUT/DELETE/assign return 403; list GET ok."""
    # GET list allowed for any login user.
    resp = await client.get("/api/llm-models")
    assert resp.status_code == 200
    resp = await client.get("/api/llm-model-assignments")
    assert resp.status_code == 200

    # POST → 403.
    resp = await client.post(
        "/api/llm-models",
        json={
            "display_name": "x",
            "model_name": "x",
            "provider_base_url": "https://x/v1",
            "context_length": 1000,
            "max_output": 1000,
            "default_max_tokens": 1000,
        },
    )
    assert resp.status_code == 403

    # PUT → 403.
    resp = await client.put("/api/llm-models/1", json={"display_name": "y"})
    assert resp.status_code == 403

    # DELETE → 403.
    resp = await client.delete("/api/llm-models/1")
    assert resp.status_code == 403

    # Assign PUT → 403.
    resp = await client.put(
        f"/api/llm-model-assignments/{STAGE_PORTRAIT}",
        json={"llm_model_id": None},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# get_stage_model / load_stage_models（接线服务层）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stage_model_returns_assigned_card(db_session):
    """get_stage_model returns the card assigned to a stage; None when unassigned."""
    session, _user = db_session
    model = LLMModel(
        display_name="svc-card",
        model_name="m-svc",
        provider_base_url="https://x/v1",
        api_key="",
        context_length=1000,
        max_output=1000,
        default_max_tokens=4000,
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    session.add(LLMModelAssignment(stage=STAGE_NORMALIZATION, llm_model_id=model.id))
    await session.commit()

    fetched = await get_stage_model(session, STAGE_NORMALIZATION)
    assert fetched is not None
    assert fetched.display_name == "svc-card"

    # Unassigned stage → None.
    assert await get_stage_model(session, STAGE_PORTRAIT) is None

    # load_stage_models returns a dict keyed by stage.
    stage_map = await load_stage_models(
        session, (STAGE_PORTRAIT, STAGE_NORMALIZATION)
    )
    assert stage_map[STAGE_PORTRAIT] is None
    assert stage_map[STAGE_NORMALIZATION].display_name == "svc-card"
