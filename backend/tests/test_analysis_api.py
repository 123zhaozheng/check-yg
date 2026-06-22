# -*- coding: utf-8 -*-
"""S6 AI 分析骨架 — agent 接入点结构测试 + API 闭环测试.

Covers (per prd §测试要求新增):
* agent 骨架结构：AuditDeps 可构造、@agent.tool 注册成功（toolset 非空 +
  JSON schema 生成）、ModelMessagesTypeAdapter 序列化往返。
* findings 列表排序（severity + confidence）.
* PATCH finding status/comment + owner-only 403.
* analyze 占位建 finding + 写 last_analysis_at.
* chat 占位回复 + history 存回 Task.config.analysis_chat_history.
"""

import pytest
from sqlalchemy import select

from app.llm.analysis import (
    AuditDeps,
    SYSTEM_PROMPT_ANALYSIS,
    chat as analysis_chat,
    get_analysis_agent,
    run_analysis,
)
from app.llm.types import AnalysisResult, FindingItem
from app.models import Finding, Task


# ---------------------------------------------------------------------------
# agent 骨架结构（conventions.md v1.107.0）
# ---------------------------------------------------------------------------


def test_audit_deps_is_constructable():
    """AuditDeps dataclass 可构造（deps_type 传类型，deps= 传实例的前提）."""
    from sqlalchemy.ext.asyncio import AsyncSession

    deps = AuditDeps(db=None, task_id=1)  # db=None for the structural test only
    assert deps.task_id == 1
    # db 字段存在（类型是 AsyncSession，构造时传实例）
    assert hasattr(deps, "db")


def test_analysis_agent_registers_three_readonly_tools():
    """@agent.tool 注册成功：toolset 非空 + 3 个工具 + JSON schema 生成.

    工具只读查 flow_records standard 记录（不删减底线）。
    """
    agent = get_analysis_agent()
    # deps_type 是 AuditDeps（类型，不是实例）
    assert agent._deps_type is AuditDeps
    # output_type 是 AnalysisResult
    assert agent._output_type is AnalysisResult

    toolset = agent._function_toolset
    tool_names = set(toolset.tools.keys())
    assert tool_names == {
        "query_transactions",
        "query_by_counterparty",
        "query_by_amount_range",
    }
    # 每个工具生成了 JSON schema（参数成 JSON schema）+ docstring 成描述.
    for name, tool in toolset.tools.items():
        assert tool.description, f"tool {name} missing description (docstring)"
        schema = tool.function_schema.json_schema
        assert schema["type"] == "object"
        assert "properties" in schema

    # 再调一次 get_analysis_agent 不重复注册（sentinel 生效）.
    agent2 = get_analysis_agent()
    assert agent is agent2
    assert set(agent2._function_toolset.tools.keys()) == tool_names


def test_system_prompt_analysis_is_placeholder_with_correct_structure():
    """SYSTEM_PROMPT_ANALYSIS 占位但结构对齐 conventions.md（任务/工具说明/输出格式）."""
    prompt = SYSTEM_PROMPT_ANALYSIS
    assert "占位" in prompt
    # 结构三段：任务 / 工具说明 / 输出格式
    assert "任务" in prompt
    assert "工具说明" in prompt
    assert "输出格式" in prompt
    # 标注是占位骨架，用户后续接真实审查逻辑
    assert "用户后续" in prompt or "真实" in prompt


def test_model_messages_type_adapter_roundtrip():
    """ModelMessagesTypeAdapter 序列化/反序列化往返（空 history）."""
    from pydantic_core import to_json

    from pydantic_ai import ModelMessagesTypeAdapter

    # 空 history 往返
    empty_json = to_json([]).decode()
    msgs = ModelMessagesTypeAdapter.validate_json(empty_json)
    assert msgs == []
    re_serialized = to_json(msgs).decode()
    assert ModelMessagesTypeAdapter.validate_json(re_serialized) == []


# ---------------------------------------------------------------------------
# run_analysis / chat 占位实现
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analysis_returns_placeholder_result(db_session):
    """run_analysis 占位返回 AnalysisResult（不调真实 LLM）."""
    session, _user = db_session
    deps = AuditDeps(db=session, task_id=999)
    result = await run_analysis(deps)
    assert isinstance(result, AnalysisResult)
    # 占位 summary 标注骨架就绪
    assert "骨架" in result.summary or "占位" in result.summary or "待接入" in result.summary
    # 占位 findings 为空（不调真实 LLM 不产垃圾输出）
    assert result.findings == []


@pytest.mark.asyncio
async def test_chat_returns_placeholder_reply_and_serializes_history(db_session):
    """chat() 占位回复 + 用 ModelMessagesTypeAdapter 序列化新 history 存回."""
    session, _user = db_session
    deps = AuditDeps(db=session, task_id=999)
    reply, new_history = await analysis_chat(deps, None, "这是一条提问")
    # 占位回复
    assert isinstance(reply, str) and reply
    assert "骨架" in reply or "待接入" in reply
    # 新 history 是合法 JSON 字符串（可被 ModelMessagesTypeAdapter 反序列化）
    assert isinstance(new_history, str)
    from pydantic_ai import ModelMessagesTypeAdapter

    ModelMessagesTypeAdapter.validate_json(new_history)  # 不抛异常即合法


# ---------------------------------------------------------------------------
# API: POST /analyze 占位建 finding + 写 last_analysis_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_creates_findings_and_writes_last_analysis_at(client, db_session):
    """POST /tasks/{id}/analyze 占位建 finding 行 + 写 task.config.last_analysis_at."""
    session, _user = db_session
    task = Task(title="Analyze", owner_id=_user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resp = await client.post(f"/api/tasks/{task.id}/analyze", json={"mode": "quick"})
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert isinstance(data["findings"], list)

    # last_analysis_at 写入 task.config
    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.config is not None
    assert "last_analysis_at" in task_row.config
    assert task_row.config["last_analysis_at"]  # ISO timestamp string


# ---------------------------------------------------------------------------
# API: GET /findings 排序（severity 降序 + confidence 降序）
# ---------------------------------------------------------------------------


async def _seed_findings(session, task_id: int) -> list[Finding]:
    """Seed findings 跨 severity + confidence，返回落库后的行列表."""
    rows = [
        Finding(
            task_id=task_id,
            type="大额",
            severity="low",
            description="低风险低置信",
            counterparty="A",
            amount="100",
            confidence=0.9,
            status="pending",
        ),
        Finding(
            task_id=task_id,
            type="高频",
            severity="high",
            description="高风险高置信",
            counterparty="B",
            amount="5000",
            confidence=0.95,
            status="pending",
        ),
        Finding(
            task_id=task_id,
            type="对手异常",
            severity="high",
            description="高风险低置信",
            counterparty="C",
            amount="3000",
            confidence=0.7,
            status="pending",
        ),
        Finding(
            task_id=task_id,
            type="金额异常",
            severity="medium",
            description="中风险中置信",
            counterparty="D",
            amount="2000",
            confidence=0.8,
            status="pending",
        ),
    ]
    session.add_all(rows)
    await session.commit()
    for r in rows:
        await session.refresh(r)
    return rows


@pytest.mark.asyncio
async def test_list_findings_sorted_by_severity_then_confidence(client, db_session):
    """GET /findings 按 severity 降序（high>medium>low），同 severity 按 confidence 降序."""
    session, _user = db_session
    task = Task(title="Findings sort", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    seeded = await _seed_findings(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    items = data["items"]
    # 期望顺序：high(0.95) > high(0.70) > medium(0.80) > low(0.90)
    assert [i["severity"] for i in items] == ["high", "high", "medium", "low"]
    assert items[0]["confidence"] == 0.95
    assert items[1]["confidence"] == 0.7
    assert items[2]["severity"] == "medium"
    assert items[3]["severity"] == "low"


@pytest.mark.asyncio
async def test_list_findings_filter_by_severity_and_status(client, db_session):
    """GET /findings?severity=&status= 过滤."""
    session, _user = db_session
    task = Task(title="Findings filter", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    seeded = await _seed_findings(session, task.id)
    # 把一条标 accepted
    seeded[0].status = "accepted"
    await session.commit()

    resp = await client.get(f"/api/tasks/{task.id}/findings?severity=high")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(i["severity"] == "high" for i in data["items"])

    resp_status = await client.get(
        f"/api/tasks/{task.id}/findings?status=accepted"
    )
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["total"] == 1
    assert status_data["items"][0]["status"] == "accepted"


# ---------------------------------------------------------------------------
# API: PATCH /findings/{id} — status/comment + owner-only 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_finding_updates_status_and_comment(client, db_session):
    """PATCH /findings/{id} 更新 status + comment."""
    session, _user = db_session
    task = Task(title="Patch", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    seeded = await _seed_findings(session, task.id)
    target = seeded[1]

    resp = await client.patch(
        f"/api/findings/{target.id}",
        json={"status": "accepted", "comment": "已确认为告警"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["comment"] == "已确认为告警"

    # DB 真实更新
    row = (
        await session.execute(select(Finding).where(Finding.id == target.id))
    ).scalar_one()
    assert row.status == "accepted"
    assert row.comment == "已确认为告警"


@pytest.mark.asyncio
async def test_patch_finding_rejects_invalid_status(client, db_session):
    """PATCH /findings/{id} status 只允许 accepted|ignored，否则 422."""
    session, _user = db_session
    task = Task(title="Patch invalid", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    seeded = await _seed_findings(session, task.id)

    resp = await client.patch(
        f"/api/findings/{seeded[0].id}",
        json={"status": "pending"},  # pending 不允许（不能改回 pending）
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_finding_owner_only_403(client, db_session):
    """非 owner 不能 patch finding（finding 所属 task 的 owner 校验）."""
    from app.models import Role, User

    session, _user = db_session
    other_role = Role(name="other_analyst")
    other = User(
        username="other",
        email="other@example.com",
        hashed_password="x",
        role=other_role,
        is_active=True,
    )
    task = Task(title="Mine patch", owner_id=_user.id, status="completed")
    session.add_all([other_role, other, task])
    await session.commit()
    await session.refresh(task)
    seeded = await _seed_findings(session, task.id)

    from app.auth.dependencies import get_current_user
    from app.main import app

    async def _other_user():
        return other

    app.dependency_overrides[get_current_user] = _other_user
    try:
        resp = await client.patch(
            f"/api/findings/{seeded[0].id}",
            json={"status": "ignored"},
        )
        assert resp.status_code == 403
    finally:
        async def _owner():
            return _user
        app.dependency_overrides[get_current_user] = _owner


@pytest.mark.asyncio
async def test_patch_finding_unknown_returns_404(client, db_session):
    session, _user = db_session
    task = Task(title="No such finding", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resp = await client.patch(
        "/api/findings/999999",
        json={"status": "ignored"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API: POST /analyze/chat — 占位回复 + history 存回 Task.config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chat_returns_reply_and_persists_history(client, db_session):
    """POST /tasks/{id}/analyze/chat 返占位回复 + 存 Task.config.analysis_chat_history."""
    session, _user = db_session
    task = Task(title="Chat", owner_id=_user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resp = await client.post(
        f"/api/tasks/{task.id}/analyze/chat",
        json={"message": "为什么这条是异常？"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert isinstance(data["reply"], str) and data["reply"]

    # history 存回 Task.config.analysis_chat_history（合法 JSON 字符串）
    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.config is not None
    history = task_row.config.get("analysis_chat_history")
    assert history
    assert isinstance(history, str)

    from pydantic_ai import ModelMessagesTypeAdapter

    ModelMessagesTypeAdapter.validate_json(history)  # 合法 message_history


# ---------------------------------------------------------------------------
# API: owner-only 403 for analyze / findings / chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_endpoints_owner_only_403(client, db_session):
    """非 owner 不能调 analyze / findings / analyze/chat."""
    from app.models import Role, User

    session, _user = db_session
    other_role = Role(name="other_analyst2")
    other = User(
        username="other2",
        email="other2@example.com",
        hashed_password="x",
        role=other_role,
        is_active=True,
    )
    task = Task(title="Mine analyze", owner_id=_user.id, status="completed")
    session.add_all([other_role, other, task])
    await session.commit()
    await session.refresh(task)

    from app.auth.dependencies import get_current_user
    from app.main import app

    async def _other_user():
        return other

    app.dependency_overrides[get_current_user] = _other_user
    try:
        resp_analyze = await client.post(
            f"/api/tasks/{task.id}/analyze", json={"mode": "quick"}
        )
        assert resp_analyze.status_code == 403
        resp_findings = await client.get(f"/api/tasks/{task.id}/findings")
        assert resp_findings.status_code == 403
        resp_chat = await client.post(
            f"/api/tasks/{task.id}/analyze/chat", json={"message": "x"}
        )
        assert resp_chat.status_code == 403
    finally:
        async def _owner():
            return _user
        app.dependency_overrides[get_current_user] = _owner
