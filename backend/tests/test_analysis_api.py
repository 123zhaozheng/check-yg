# -*- coding: utf-8 -*-
"""06-26-ai-agent AI 审查 agent —— 工具/维度/会话/重跑策略测试.

Covers (PRD §十一 单测要求):
* 5 个只读工具纯逻辑（get_task_summary / query_by_time 剔 00:00:00 /
  query_by_amount mode / query_by_counterparty min_count / query_burst）。
* create_dimension 白名单校验（编造工具名 → ModelRetry；落 source=agent /
  enabled=false / created_by）。
* 维度 prompt 拼装（build_dimension_prompt 含固定段 + 字段段 + few-shot）。
* 重跑保留策略（只删 pending finding，保留 accepted/ignored）。
* agent 骨架结构：AuditDeps 可构造、ReadAuditToolset 5 工具注册 + JSON schema、
  ModelMessagesTypeAdapter 序列化往返、维度/追问 agent 单例 + per-dimension 单例。
* API: POST /analyze 异步启动 + 409 重入；GET /findings 排序；PATCH /findings
  owner-only 403；POST /analyze/chat（mock LLM）多会话；会话列表/新建/删除；
  维度 CRUD admin 鉴权 + 409 finding 引用。
"""

import asyncio
from datetime import datetime, timezone

import pytest
from pydantic_ai import ModelMessagesTypeAdapter, ModelRetry
from pydantic_core import to_json
from sqlalchemy import select

from app.llm.analysis import (
    READONLY_TOOL_WHITELIST,
    AuditDeps,
    build_read_audit_toolset,
    get_dimension_agent,
    get_qa_agent,
    _clamp_limit,
    _has_hms,
)
from app.llm.types import DimensionFinding, DimensionFindingResult
from app.models import (
    AuditConversation,
    AuditDimension,
    Finding,
    FlowRecordRow,
    Task,
)
from app.services.audit.dimension_prompt import build_dimension_prompt
from app.services.audit.system_dimensions import system_dimension_rows


# ---------------------------------------------------------------------------
# agent 骨架结构（conventions.md v1.107.0）
# ---------------------------------------------------------------------------


def test_audit_deps_is_constructable():
    """AuditDeps dataclass 可构造（deps_type 传类型，deps= 传实例的前提）."""
    deps = AuditDeps(db=None, task_id=1, user_id=2)
    assert deps.task_id == 1
    assert deps.user_id == 2
    assert hasattr(deps, "db")


def test_read_audit_toolset_registers_five_readonly_tools():
    """ReadAuditToolset 注册 5 个只读工具 + JSON schema 生成."""
    ts = build_read_audit_toolset()
    tool_names = set(ts.tools.keys())
    assert tool_names == {
        "get_task_summary",
        "query_by_time",
        "query_by_amount",
        "query_by_counterparty",
        "query_burst",
    }
    for name, tool in ts.tools.items():
        assert tool.description, f"tool {name} missing description (docstring)"
        schema = tool.function_schema.json_schema
        assert schema["type"] == "object"
        assert "properties" in schema


def test_dimension_agent_singleton_per_prompt():
    """维度 agent：同 prompt 同单例；不同 prompt 不同单例；output=DimensionFindingResult."""
    p1 = build_dimension_prompt("夜间交易", "查夜间", [{"tool": "query_by_time", "params": {"hours": [22]}}], "命中high", "high")
    p2 = build_dimension_prompt("大额交易", "查大额", [{"tool": "query_by_amount", "params": {"mode": "large"}}], ">=5万high", "high")
    da1 = get_dimension_agent(p1)
    da2 = get_dimension_agent(p1)
    da3 = get_dimension_agent(p2)
    assert da1 is da2, "same prompt -> same cached agent"
    assert da1 is not da3, "different prompt -> different agent"
    assert da1._output_type is DimensionFindingResult
    assert da1._deps_type is AuditDeps


def test_qa_agent_singleton_and_extra_tools():
    """追问 agent 单例 + 挂只读 Toolset（_user_toolsets）+ query_findings/create_dimension（_function_toolset）."""
    qa1 = get_qa_agent()
    qa2 = get_qa_agent()
    assert qa1 is qa2, "qa agent cached singleton"
    assert qa1._output_type is str
    # 只读 5 工具在 _user_toolsets
    user_tools = set()
    for ts in qa1._user_toolsets:
        user_tools |= set(ts.tools.keys())
    assert user_tools == {
        "get_task_summary", "query_by_time", "query_by_amount",
        "query_by_counterparty", "query_burst",
    }
    # query_findings + create_dimension 在 _function_toolset
    assert set(qa1._function_toolset.tools.keys()) == {"query_findings", "create_dimension"}
    # 再调一次不重复注册（sentinel 生效）
    assert set(qa1._function_toolset.tools.keys()) == {"query_findings", "create_dimension"}


def test_model_messages_type_adapter_roundtrip():
    """ModelMessagesTypeAdapter 序列化/反序列化往返（空 history）."""
    empty_json = to_json([]).decode()
    msgs = ModelMessagesTypeAdapter.validate_json(empty_json)
    assert msgs == []
    re_serialized = to_json(msgs).decode()
    assert ModelMessagesTypeAdapter.validate_json(re_serialized) == []


# ---------------------------------------------------------------------------
# 纯逻辑助手：_has_hms / _clamp_limit / build_dimension_prompt
# ---------------------------------------------------------------------------


def test_has_hms_filters_date_only_noise():
    """_has_hms 剔除「只记日期」噪音（00:00:00 视为噪音，不可关）."""
    assert _has_hms("2026-06-15 23:45:00") is True
    assert _has_hms("2026-06-15 00:30:00") is True
    assert _has_hms("2026-06-15 00:00:00") is False  # 全 0 噪音
    assert _has_hms("2026-06-15") is False  # 仅日期
    assert _has_hms("") is False
    assert _has_hms(None) is False


def test_clamp_limit_default_and_hard_cap():
    """_clamp_limit：默认 200，硬上限 1000，<1 归 1."""
    assert _clamp_limit(None) == 200
    assert _clamp_limit(5000) == 1000
    assert _clamp_limit(0) == 1
    assert _clamp_limit(150) == 150


def test_build_dimension_prompt_contains_fixed_and_field_sections():
    """build_dimension_prompt 含固定段（工具说明/few-shot）+ 字段段（purpose/steps/judgment）."""
    p = build_dimension_prompt(
        name="夜间交易",
        purpose="检测夜间交易。",
        steps=[{"tool": "query_by_time", "params": {"hours": [22, 23]}}],
        judgment="命中即 high。",
        severity="high",
    )
    assert "## 维度：夜间交易" in p
    assert "默认severity: high" in p
    assert "## 任务" in p
    assert "检测夜间交易" in p
    assert "可用工具" in p  # 固定段
    assert "query_by_time" in p  # steps 格式化
    assert "## 判定标准" in p
    assert "命中即 high" in p
    assert "样例" in p  # few-shot 固定段
    # 空步骤分支
    p2 = build_dimension_prompt("空", "查", None, "零命中空", "low")
    assert "按需自行调用工具" in p2


def test_system_dimensions_seed_rows_built():
    """5 个 system 维度 seed 行：source=system / enabled=true / created_by=None / prompt 已拼."""
    rows = system_dimension_rows()
    assert len(rows) == 5
    names = {r["name"] for r in rows}
    assert names == {"夜间交易", "大额交易", "整数金额", "重复对手方", "短间隔簇"}
    for r in rows:
        assert r["source"] == "system"
        assert r["enabled"] is True
        assert r["created_by"] is None
        assert r["prompt"] and "## 维度" in r["prompt"]


# ---------------------------------------------------------------------------
# 5 个只读工具纯逻辑（DB 驱动）
# ---------------------------------------------------------------------------


async def _seed_standard_rows(session, task_id: int) -> None:
    """Seed 7 standard rows 覆盖夜间/大额/整数/重复对手/短间隔/噪音."""
    rows = [
        FlowRecordRow(
            task_id=task_id, record_type="standard", row_index=i, is_valid=True,
            transaction_time=tt, counterparty_name=cp, amount=amt, summary="s",
            transaction_type="income",
        )
        for i, (tt, cp, amt) in enumerate(
            [
                ("2026-06-15 23:45:00", "对手A", "30000"),   # 夜间 + 整数(4个0)
                ("2026-06-15 00:30:00", "对手A", "500"),      # 夜间
                ("2026-06-16 10:00:00", "对手B", "100000"),   # 大额 + 整数(5个0)
                ("2026-06-16 11:00:00", "对手B", "20000"),    # 整数 + 短间隔簇
                ("2026-06-16 11:20:00", "对手B", "20000"),    # 整数 + 短间隔簇(<=30min)
                ("2026-06-16 12:00:00", "对手C", "5000"),
                ("2026-06-16 00:00:00", "对手D", "999"),      # 00:00:00 噪音
            ],
            start=1,
        )
    ]
    session.add_all(rows)
    await session.commit()


class _FakeCtx:
    """最小 RunContext 替身（供工具 function 直调）."""

    def __init__(self, deps: AuditDeps):
        self.deps = deps


@pytest.mark.asyncio
async def test_tool_get_task_summary(db_session):
    """get_task_summary 返聚合数（standard 计数 + unparsed 计数 + 金额合计 + 时间跨度）."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_standard_rows(session, task.id)
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    ts = build_read_audit_toolset()
    summary = await ts.tools["get_task_summary"].function(_FakeCtx(deps))
    assert summary["standard_count"] == 7
    assert "total_amount" in summary
    assert "time_span" in summary


@pytest.mark.asyncio
async def test_tool_query_by_time_filters_night_and_noise(db_session):
    """query_by_time hours=[22,23,0,1,2,3,4,5] 返夜间行，剔除 00:00:00 噪音."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_standard_rows(session, task.id)
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    ts = build_read_audit_toolset()
    night = await ts.tools["query_by_time"].function(
        _FakeCtx(deps), hours=[22, 23, 0, 1, 2, 3, 4, 5]
    )
    # 23:45 + 00:30 = 2（00:00:00 噪音剔除，date-only 剔除）
    assert len(night) == 2
    assert all(r["transaction_time"] for r in night)


@pytest.mark.asyncio
async def test_tool_query_by_amount_modes(db_session):
    """query_by_amount: large/round/evasion 三种 mode."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_standard_rows(session, task.id)
    # 补一条 evasion band 内（40000-50000）
    session.add(FlowRecordRow(
        task_id=task.id, record_type="standard", row_index=99, is_valid=True,
        transaction_time="2026-06-17 09:00:00", counterparty_name="对手E",
        amount="45000", summary="s", transaction_type="income",
    ))
    await session.commit()
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    ts = build_read_audit_toolset()
    # large: >=50000 -> 100000 only
    large = await ts.tools["query_by_amount"].function(_FakeCtx(deps), mode="large", min=50000)
    assert [r["amount"] for r in large] == ["100000"]
    # round: 尾随>=4个0 -> 30000/100000/20000/20000
    rnd = await ts.tools["query_by_amount"].function(_FakeCtx(deps), mode="round")
    assert sorted(r["amount"] for r in rnd) == ["100000", "20000", "20000", "30000"]
    # evasion: <50000 且 >=40000 -> 45000
    ev = await ts.tools["query_by_amount"].function(_FakeCtx(deps), mode="evasion", min=50000)
    assert [r["amount"] for r in ev] == ["45000"]


@pytest.mark.asyncio
async def test_tool_query_by_counterparty_min_count(db_session):
    """query_by_counterparty min_count=2 一步出「>=2 笔的对手方」聚合."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_standard_rows(session, task.id)
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    ts = build_read_audit_toolset()
    agg = await ts.tools["query_by_counterparty"].function(_FakeCtx(deps), min_count=2)
    cps = {c["counterparty_name"]: c["count"] for c in agg}
    assert cps.get("对手A") == 2
    assert cps.get("对手B") == 3
    assert "对手C" not in cps  # 1 笔，不满足 min_count=2


@pytest.mark.asyncio
async def test_tool_query_burst_clusters_within_window(db_session):
    """query_burst window=30 min_count=2：对手B(11:00,11:20)成簇；对手A(23:45,00:30)45分钟不成簇."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_standard_rows(session, task.id)
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    ts = build_read_audit_toolset()
    bursts = await ts.tools["query_burst"].function(
        _FakeCtx(deps), window_minutes=30, min_count=2
    )
    bcp = {b["counterparty_name"]: b["count"] for b in bursts}
    assert bcp.get("对手B") == 2
    assert "对手A" not in bcp  # 23:45 -> 00:30 是 45 分钟，不成簇


# ---------------------------------------------------------------------------
# create_dimension 白名单校验 + 沉淀
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dimension_rejects_unknown_tool(db_session):
    """create_dimension: steps.tool 编造 → ModelRetry."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add_all([task])
    await session.commit()
    await session.refresh(user)
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    qa = get_qa_agent()
    create_dim = qa._function_toolset.tools["create_dimension"]
    with pytest.raises(ModelRetry):
        await create_dim.function(
            _FakeCtx(deps),
            name="x", purpose="y",
            steps=[{"tool": "fake_tool", "params": {}}],
            judgment="z", severity="low",
        )


@pytest.mark.asyncio
async def test_create_dimension_rejects_bad_severity_and_empty_steps(db_session):
    """create_dimension: 非法 severity / 空 steps → ModelRetry."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add_all([task])
    await session.commit()
    await session.refresh(user)
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    qa = get_qa_agent()
    create_dim = qa._function_toolset.tools["create_dimension"]
    with pytest.raises(ModelRetry):
        await create_dim.function(
            _FakeCtx(deps), name="x", purpose="y",
            steps=[{"tool": "query_by_time", "params": {}}],
            judgment="z", severity="critical",
        )
    with pytest.raises(ModelRetry):
        await create_dim.function(
            _FakeCtx(deps), name="x", purpose="y", steps=[],
            judgment="z", severity="low",
        )


@pytest.mark.asyncio
async def test_create_dimension_persists_agent_draft(db_session):
    """create_dimension: 合法入参 → 落 AuditDimension(source=agent, enabled=false, created_by)."""
    session, user = db_session
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add_all([task])
    await session.commit()
    await session.refresh(user)
    deps = AuditDeps(db=session, task_id=task.id, user_id=user.id)
    qa = get_qa_agent()
    create_dim = qa._function_toolset.tools["create_dimension"]
    msg = await create_dim.function(
        _FakeCtx(deps),
        name="阈值规避", purpose="查阈值下浮band内交易",
        steps=[{"tool": "query_by_amount", "params": {"mode": "evasion", "min": 50000}}],
        judgment="band内>=3笔high", severity="high",
    )
    # create_dimension 返结构化 dict（PRD §六）：含 id/name/severity/enabled/message。
    assert isinstance(msg, dict)
    assert msg["name"] == "阈值规避"
    assert msg["severity"] == "high"
    assert msg["enabled"] is False
    assert "草稿" in msg["message"] or "enabled=false" in msg["message"]
    dim = (
        await session.execute(select(AuditDimension).where(AuditDimension.name == "阈值规避"))
    ).scalar_one()
    assert dim.source == "agent"
    assert dim.enabled is False  # 草稿，需人审启用
    assert dim.created_by == user.id
    assert "## 维度：阈值规避" in dim.prompt


# ---------------------------------------------------------------------------
# API: POST /analyze 异步启动 + 409 重入 + 重跑保留策略
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_starts_async_and_writes_last_analysis_at(client, db_session, monkeypatch):
    """POST /tasks/{id}/analyze 异步启动，立即返 status=started + 写 last_analysis_at."""
    session, user = db_session
    task = Task(title="Analyze", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # mock run_dimension 避免真调 LLM（返零命中，不建 finding）。
    async def _fake_run_dimension(deps, dimension, *, model=None):
        return DimensionFindingResult(findings=[], summary=f"{dimension.name}：未发现异常")

    monkeypatch.setattr(
        "app.services.audit.analysis_service.run_dimension", _fake_run_dimension
    )
    # seed 一个 enabled 维度（system seed 在 sqlite 由 system_dimension_rows 提供，
    # 但测试库无迁移；手动建一条）。
    from app.models import AuditDimension
    session.add(AuditDimension(
        name="夜间交易", source="system", purpose="查夜间",
        steps=[{"tool": "query_by_time", "params": {"hours": [22]}}],
        judgment="命中high", severity="high",
        prompt=build_dimension_prompt("夜间交易", "查夜间", [{"tool": "query_by_time", "params": {"hours": [22]}}], "命中high", "high"),
        enabled=True,
    ))
    await session.commit()

    resp = await client.post(f"/api/tasks/{task.id}/analyze", json={"mode": "quick"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["task_id"] == task.id
    assert data["total_dimensions"] == 1

    # 等 background task 跑完。
    from app.services.audit.analysis_service import analysis_service
    for _ in range(50):
        if not analysis_service.is_running(task.id):
            break
        await asyncio.sleep(0.05)

    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.config is not None
    assert "last_analysis_at" in task_row.config


@pytest.mark.asyncio
async def test_analyze_rerun_keeps_accepted_ignored_findings(client, db_session, monkeypatch):
    """重跑策略：只删 pending finding，保留 accepted/ignored 人工结论."""
    session, user = db_session
    task = Task(title="Rerun", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # seed 一个 enabled 维度 + 三条不同 status 的 finding（其中两条 dimension_id 指向该维度）。
    from app.models import AuditDimension
    dim = AuditDimension(
        name="夜间交易", source="system", purpose="查夜间",
        steps=[{"tool": "query_by_time", "params": {"hours": [22]}}],
        judgment="命中high", severity="high",
        prompt=build_dimension_prompt("夜间交易", "查夜间", [{"tool": "query_by_time", "params": {"hours": [22]}}], "命中high", "high"),
        enabled=True,
    )
    session.add(dim)
    await session.flush()
    pending = Finding(task_id=task.id, type="夜间交易", severity="high", description="d1", confidence=0.9, status="pending", dimension_id=dim.id, source="rule")
    accepted = Finding(task_id=task.id, type="大额交易", severity="high", description="d2", confidence=0.8, status="accepted")
    ignored = Finding(task_id=task.id, type="对手异常", severity="medium", description="d3", confidence=0.7, status="ignored")
    session.add_all([pending, accepted, ignored])
    await session.commit()

    # mock run_dimension 返零命中（不建新 finding）。
    async def _fake_run_dimension(deps, dimension, *, model=None):
        return DimensionFindingResult(findings=[], summary="未发现")
    monkeypatch.setattr(
        "app.services.audit.analysis_service.run_dimension", _fake_run_dimension
    )

    resp = await client.post(f"/api/tasks/{task.id}/analyze", json={})
    assert resp.status_code == 200

    from app.services.audit.analysis_service import analysis_service
    for _ in range(50):
        if not analysis_service.is_running(task.id):
            break
        await asyncio.sleep(0.05)

    # pending 被删；accepted/ignored 保留。
    remaining = (
        await session.execute(select(Finding).where(Finding.task_id == task.id))
    ).scalars().all()
    statuses = {f.status for f in remaining}
    assert "pending" not in statuses, "pending finding should be deleted on rerun"
    assert "accepted" in statuses and "ignored" in statuses


@pytest.mark.asyncio
async def test_analyze_409_when_already_running(client, db_session, monkeypatch):
    """分析已在跑 → POST /analyze 返 409."""
    session, user = db_session
    task = Task(title="Running", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    from app.services.audit.analysis_service import analysis_service

    # 占位 _jobs 让 is_running 返 True。
    analysis_service._jobs[task.id] = asyncio.get_event_loop().create_future() if False else asyncio.Future()
    try:
        resp = await client.post(f"/api/tasks/{task.id}/analyze", json={})
        assert resp.status_code == 409
    finally:
        analysis_service._jobs.pop(task.id, None)


@pytest.mark.asyncio
async def test_analyze_writes_incremental_progress_to_config(client, db_session, monkeypatch):
    """每跑完一个维度增量推 completed（PRD §十一 验收项：进度条按已完成/总数走）.

    跑 2 个维度：mock run_dimension 返零命中，mock notify_user 捕获每条
    ``analysis.progress`` 的 ``resource.completed``，断言中途递增 1→2
    （即每维度完增量推进度，非只在结束时一次性写）。

    patch ``analysis_service.async_session`` 让 background job 用测试的 sqlite
    session（默认 ``async_session`` 指 PG，与测试 sqlite 库隔离），保证可重现。
    """
    session, user = db_session
    task = Task(title="Progress", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    from app.models import AuditDimension

    for nm in ("夜间交易", "大额交易"):
        session.add(AuditDimension(
            name=nm, source="system", purpose="查",
            steps=[{"tool": "query_by_time", "params": {}}],
            judgment="命中high", severity="high",
            prompt=build_dimension_prompt(nm, "查", [{"tool": "query_by_time", "params": {}}], "命中high", "high"),
            enabled=True,
        ))
    await session.commit()

    async def _fake_run_dimension(deps, dimension, *, model=None):
        return DimensionFindingResult(findings=[], summary=f"{dimension.name}：未发现异常")

    monkeypatch.setattr(
        "app.services.audit.analysis_service.run_dimension", _fake_run_dimension
    )

    # background job 用测试 sqlite session（复用 db_session 的 session）。
    class _SessionCtx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(
        "app.services.audit.analysis_service.async_session", lambda: _SessionCtx()
    )

    # 捕获 analysis.progress 的 resource.completed（含最终完成通知）。
    progress_completed: list[int] = []

    async def _capture_notify(user_id, *, event, title, message, resource):
        if event == "analysis.progress":
            progress_completed.append(int(resource.get("completed") or 0))

    monkeypatch.setattr(
        "app.services.audit.analysis_service.notify_user", _capture_notify
    )

    resp = await client.post(f"/api/tasks/{task.id}/analyze", json={"mode": "quick"})
    assert resp.status_code == 200
    assert resp.json()["total_dimensions"] == 2

    from app.services.audit.analysis_service import analysis_service
    for _ in range(80):
        if not analysis_service.is_running(task.id):
            break
        await asyncio.sleep(0.05)

    # 每维度完推一条 completed=1，再 completed=2（中途递增，非一次性）。
    # 末尾还有一条「分析完成」通知（completed=2），故取前两条维度进度。
    per_dim = progress_completed[:2]
    assert per_dim == [1, 2], f"completed should increment per dimension: {progress_completed}"
    # 跑完总数对齐。
    assert progress_completed[-1] == 2


# ---------------------------------------------------------------------------
# API: GET /findings 排序 + PATCH /findings owner-only
# ---------------------------------------------------------------------------


async def _seed_findings(session, task_id: int) -> list[Finding]:
    rows = [
        Finding(task_id=task_id, type="大额", severity="low", description="低风险低置信",
                counterparty="A", amount="100", confidence=0.9, status="pending"),
        Finding(task_id=task_id, type="高频", severity="high", description="高风险高置信",
                counterparty="B", amount="5000", confidence=0.95, status="pending"),
        Finding(task_id=task_id, type="对手异常", severity="high", description="高风险低置信",
                counterparty="C", amount="3000", confidence=0.7, status="pending"),
        Finding(task_id=task_id, type="金额异常", severity="medium", description="中风险中置信",
                counterparty="D", amount="2000", confidence=0.8, status="pending"),
    ]
    session.add_all(rows)
    await session.commit()
    for r in rows:
        await session.refresh(r)
    return rows


@pytest.mark.asyncio
async def test_list_findings_sorted_by_severity_then_confidence(client, db_session):
    """GET /findings 按 severity 降序，同 severity 按 confidence 降序."""
    session, _user = db_session
    task = Task(title="Findings sort", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_findings(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/findings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    items = data["items"]
    assert [i["severity"] for i in items] == ["high", "high", "medium", "low"]
    assert items[0]["confidence"] == 0.95
    assert items[1]["confidence"] == 0.7
    # 新增 additive 字段在响应里（历史 finding 为 None）。
    assert items[0]["dimension_id"] is None
    assert items[0]["source"] is None


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


@pytest.mark.asyncio
async def test_patch_finding_owner_only_403(client, db_session):
    """非 owner 不能 patch finding."""
    from app.models import Role, User

    session, _user = db_session
    other_role = Role(name="other_analyst")
    other = User(username="other", email="other@example.com", hashed_password="x",
                 role=other_role, is_active=True)
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
        resp = await client.patch(f"/api/findings/{seeded[0].id}", json={"status": "ignored"})
        assert resp.status_code == 403
    finally:
        async def _owner():
            return _user
        app.dependency_overrides[get_current_user] = _owner


# ---------------------------------------------------------------------------
# API: POST /analyze/chat（mock LLM）多会话 + 会话列表/新建/删除
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_chat_creates_conversation_and_persists_history(client, db_session, monkeypatch):
    """POST /analyze/chat（无 conversation_id）新建会话 + 存 message_history + 返 conv_id."""
    session, user = db_session
    task = Task(title="Chat", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # mock agent_chat 避免真调 LLM（返零工具痕迹的 ChatResult）。
    from app.llm.analysis import ChatResult

    async def _fake_chat(deps, history_json, user_msg, *, model=None):
        return ChatResult(
            reply="这是 mock 回复",
            tool_traces=[],
            sedimented_dimension=None,
            new_history_json=to_json([]).decode(),
        )

    monkeypatch.setattr("app.services.audit.analysis_service.agent_chat", _fake_chat)

    resp = await client.post(
        f"/api/tasks/{task.id}/analyze/chat",
        json={"message": "为什么这条是异常？", "conversation_id": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == "这是 mock 回复"
    assert isinstance(data["conversation_id"], int)
    # 新增字段向后兼容：默认空 traces / None sedimented。
    assert data["tool_traces"] == []
    assert data["sedimented_dimension"] is None

    # 会话落库 + title=首问题前 10 字。
    conv = (
        await session.execute(
            select(AuditConversation).where(AuditConversation.id == data["conversation_id"])
        )
    ).scalar_one()
    assert conv.task_id == task.id
    assert conv.title == "为什么这条是异常？"[:10]


@pytest.mark.asyncio
async def test_analyze_chat_exposes_tool_traces_and_sedimented(client, db_session, monkeypatch):
    """POST /analyze/chat 响应暴露 tool_traces + sedimented_dimension（PRD §十 验收项）.

    mock agent_chat 返带工具调用痕迹 + 沉淀维度的 ChatResult → 断言响应里
    tool_traces 非空、sedimented_dimension 含 name + severity。
    """
    session, user = db_session
    task = Task(title="ChatTrace", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    from app.llm.analysis import ChatResult, SedimentedDimension, ToolTrace

    async def _fake_chat(deps, history_json, user_msg, *, model=None):
        return ChatResult(
            reply="夜间交易共 37 条",
            tool_traces=[
                ToolTrace(tool="query_by_time", summary="返回 37 条"),
                ToolTrace(tool="get_task_summary", summary="standard 100 条"),
            ],
            sedimented_dimension=SedimentedDimension(name="阈值规避", severity="high"),
            new_history_json=to_json([]).decode(),
        )

    monkeypatch.setattr("app.services.audit.analysis_service.agent_chat", _fake_chat)

    resp = await client.post(
        f"/api/tasks/{task.id}/analyze/chat",
        json={"message": "沉淀一个阈值规避维度", "conversation_id": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tool_traces"]) == 2
    assert data["tool_traces"][0]["tool"] == "query_by_time"
    assert data["tool_traces"][0]["summary"] == "返回 37 条"
    assert data["sedimented_dimension"] == {"name": "阈值规避", "severity": "high"}


@pytest.mark.asyncio
async def test_chat_extracts_traces_from_real_message_history(db_session):
    """chat() 从 result.all_messages() 解析 ToolCallPart/ToolReturnPart 出 traces.

    不真调 LLM：直接喂 _extract_tool_traces / _extract_sedimented_dimension
    构造的 message 列表，验按 tool_call_id 配对 + create_dimension 提取。
    """
    from app.llm.analysis import (
        ChatResult,
        _extract_sedimented_dimension,
        _extract_tool_traces,
    )
    from app.llm.types import DimensionFindingResult
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    # 构造一轮带两次工具调用的 message history。
    call1 = ToolCallPart(tool_name="query_by_time", tool_call_id="c1")
    call2 = ToolCallPart(tool_name="create_dimension", tool_call_id="c2")
    messages = [
        ModelRequest(parts=[UserPromptPart(content="查夜间")]),
        ModelResponse(parts=[call1]),
        ModelRequest(parts=[ToolReturnPart(tool_name="query_by_time", tool_call_id="c1", content=[{"id": 1}, {"id": 2}])]),
        ModelResponse(parts=[call2]),
        ModelRequest(parts=[ToolReturnPart(tool_name="create_dimension", tool_call_id="c2", content={"id": 9, "name": "阈值规避", "severity": "high", "enabled": False})]),
    ]

    traces = _extract_tool_traces(messages)
    assert [t.tool for t in traces] == ["query_by_time", "create_dimension"]
    assert "2" in traces[0].summary  # list len

    sedimented = _extract_sedimented_dimension(messages)
    assert sedimented is not None
    assert sedimented.name == "阈值规避"
    assert sedimented.severity == "high"


@pytest.mark.asyncio
async def test_conversations_list_create_delete(client, db_session):
    """GET/POST/DELETE /tasks/{id}/analyze/conversations[/{id}] 会话 CRUD."""
    session, user = db_session
    task = Task(title="Conv", owner_id=user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    # 新建
    resp = await client.post(
        f"/api/tasks/{task.id}/analyze/conversations", json={"title": "第一个问题"}
    )
    assert resp.status_code == 201
    conv_id = resp.json()["id"]

    # 列表
    resp = await client.get(f"/api/tasks/{task.id}/analyze/conversations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(c["id"] == conv_id for c in data["items"])

    # 删除
    resp = await client.delete(
        f"/api/tasks/{task.id}/analyze/conversations/{conv_id}"
    )
    assert resp.status_code == 204

    # 删后列表不含
    resp = await client.get(f"/api/tasks/{task.id}/analyze/conversations")
    assert all(c["id"] != conv_id for c in resp.json()["items"])


# ---------------------------------------------------------------------------
# API: 维度 CRUD admin 鉴权 + 409 finding 引用
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_dimensions_admin_crud(client, db_session):
    """admin 能 CRUD 维度；非 admin POST 返 403."""
    session, user = db_session
    # conftest 的 user 角色是 auditor（非 admin）→ POST 应 403。
    resp = await client.post(
        "/api/audit-dimensions",
        json={
            "name": "夜间交易",
            "purpose": "查夜间",
            "steps": [{"tool": "query_by_time", "params": {"hours": [22]}}],
            "judgment": "命中high",
            "severity": "high",
        },
    )
    assert resp.status_code == 403

    # 升级为 admin。
    from app.models import Role
    from sqlalchemy import select as _sel
    admin_role = Role(name="admin")
    session.add(admin_role)
    await session.commit()
    await session.refresh(admin_role)
    user.role_id = admin_role.id
    await session.commit()

    resp = await client.post(
        "/api/audit-dimensions",
        json={
            "name": "夜间交易",
            "purpose": "查夜间",
            "steps": [{"tool": "query_by_time", "params": {"hours": [22]}}],
            "judgment": "命中high",
            "severity": "high",
        },
    )
    assert resp.status_code == 201
    dim_id = resp.json()["id"]
    assert resp.json()["prompt"].startswith("## 维度：夜间交易")

    # GET 列表 + 详情
    assert (await client.get("/api/audit-dimensions")).status_code == 200
    detail = await client.get(f"/api/audit-dimensions/{dim_id}")
    assert detail.status_code == 200
    assert detail.json()["steps"][0]["tool"] == "query_by_time"

    # PUT 改 enabled + severity
    resp = await client.put(
        f"/api/audit-dimensions/{dim_id}",
        json={"enabled": False, "severity": "medium"},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert resp.json()["severity"] == "medium"
    assert "默认severity: medium" in resp.json()["prompt"]  # prompt 重拼

    # DELETE
    resp = await client.delete(f"/api/audit-dimensions/{dim_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_audit_dimension_delete_409_when_finding_referenced(client, db_session):
    """删维度时已被 finding 引用 → 409."""
    session, user = db_session
    from app.models import Role
    admin_role = Role(name="admin")
    session.add(admin_role)
    await session.commit()
    await session.refresh(admin_role)
    user.role_id = admin_role.id
    task = Task(title="t", owner_id=user.id, status="completed", config={})
    session.add_all([task])
    await session.commit()
    await session.refresh(task)

    # 建维度。
    resp = await client.post(
        "/api/audit-dimensions",
        json={
            "name": "整数金额", "purpose": "查整数",
            "steps": [{"tool": "query_by_amount", "params": {"mode": "round"}}],
            "judgment": "集中medium", "severity": "medium",
        },
    )
    assert resp.status_code == 201
    dim_id = resp.json()["id"]

    # 建一条 finding 引用该维度。
    session.add(Finding(
        task_id=task.id, type="整数金额", severity="medium", description="d",
        confidence=0.8, status="pending", dimension_id=dim_id, source="rule",
    ))
    await session.commit()

    # 删 → 409。
    resp = await client.delete(f"/api/audit-dimensions/{dim_id}")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# API: owner-only 403 for analyze / findings / chat / conversations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_endpoints_owner_only_403(client, db_session):
    """非 owner 不能调 analyze / findings / analyze/chat / conversations."""
    from app.models import Role, User

    session, _user = db_session
    other_role = Role(name="other_analyst2")
    other = User(username="other2", email="other2@example.com", hashed_password="x",
                 role=other_role, is_active=True)
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
        assert (await client.post(f"/api/tasks/{task.id}/analyze", json={"mode": "quick"})).status_code == 403
        assert (await client.get(f"/api/tasks/{task.id}/findings")).status_code == 403
        assert (await client.post(f"/api/tasks/{task.id}/analyze/chat", json={"message": "x"})).status_code == 403
        assert (await client.get(f"/api/tasks/{task.id}/analyze/conversations")).status_code == 403
    finally:
        async def _owner():
            return _user
        app.dependency_overrides[get_current_user] = _owner
