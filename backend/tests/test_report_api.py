# -*- coding: utf-8 -*-
"""S7 审查报告闭环 API tests.

Covers (per prd §验证 新增后端单测):
* 报告生成建 8 章（异步 background job；mock agent 避免真 LLM 调用）.
* 章节编辑（PATCH content）.
* 单章重生成（mock agent run_chapter）.
* 拖拽排序（reorder）.
* 批注增 + 切 resolved.
* 定稿后写操作 409（编辑/重生成/reorder/新建批注/切 resolved）.
* owner 校验 403.

06-28 Phase 2：生成改异步（generating→generated）。测试 mock
``app.llm.report_agent.run_chapter`` 避免真 LLM 调用；background job 用
独立 ``async_session``（测试内存 sqlite 不共享），故生成后**同步**调
``build_all_chapters`` 兜底验证模板逻辑，生成 endpoint 只验 generating 态。
"""

import pytest
from sqlalchemy import select

from app.models import Report, ReportAnnotation, ReportChapter, Task
from app.services.report_chapter_builder import chapter_titles


async def _seed_task(session, user_id: int) -> Task:
    """Seed a completed task owned by user_id with config (cleaning_committed)."""
    task = Task(
        title="报告闭环测试",
        owner_id=user_id,
        status="completed",
        config={"cleaning_committed": "2026-06-20 10:00"},
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def _mark_report_generated(session, report_id: int) -> None:
    """测试 helper：后台生成完成后，写接口才允许编辑/重生成/批注/定稿."""
    row = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one()
    row.status = "generated"
    await session.commit()


@pytest.fixture(autouse=True)
def _mock_report_agent(monkeypatch):
    """Mock run_chapter 避免真 LLM 调用（所有报告 API 测试默认 mock）.

    mock 返一段固定 markdown（含章节标题），让 build_all_chapters / regenerate
    不走真 LLM 也不因连接失败回退模板（可验 LLM 路径产物）。
    """
    async def _fake_run_chapter(deps, chapter_title, context_json, *, model=None):
        return f"## {chapter_title}\n\nLLM 生成的正文（mock）。"

    # mock report_agent.run_chapter（build_all_chapters / build_one_chapter 调它）。
    monkeypatch.setattr(
        "app.services.report_chapter_builder.run_chapter", _fake_run_chapter
    )
    yield


# ---------------------------------------------------------------------------
# 生成 8 章 + 幂等
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_report_creates_six_chapters(client, db_session):
    """POST /tasks/{id}/report 建 Report(status=generating) + 8 个空 ReportChapter.

    06-28 Phase 2：生成改异步，endpoint 立即返 generating + 8 空章（content=""）。
    background job 在独立 async_session 跑（测试内存 sqlite 不共享），故此处只验
    generating 态 + 8 章结构；LLM 填充由 build_all_chapters 单测覆盖。
    """
    session, user = db_session
    task = await _seed_task(session, user.id)

    resp = await client.post(f"/api/tasks/{task.id}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == task.id
    assert body["status"] == "generating"
    assert body["review_id"] is None
    chapters = body["chapters"]
    assert len(chapters) == 8
    # 8 章固定标题 + order_index 0-7.
    assert [c["title"] for c in chapters] == [
        "概述", "被审查对象", "数据范围", "完整性校验（余额）",
        "关键词审查", "异常发现汇总", "风险评估", "结论建议",
    ]
    assert [c["order_index"] for c in chapters] == [0, 1, 2, 3, 4, 5, 6, 7]

    # DB 真实落 8 行 ReportChapter（生成中 content 为空）。
    rows = (
        await session.execute(
            select(ReportChapter).where(ReportChapter.report_id == body["id"])
        )
    ).scalars().all()
    assert len(rows) == 8
    assert all(r.content == "" for r in rows)


@pytest.mark.asyncio
async def test_generate_report_is_idempotent(client, db_session):
    """幂等：task 已有 draft 报告则返已有，不重复建."""
    session, user = db_session
    task = await _seed_task(session, user.id)

    first = await client.post(f"/api/tasks/{task.id}/report")
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = await client.post(f"/api/tasks/{task.id}/report")
    assert second.status_code == 200
    assert second.json()["id"] == first_id

    # DB 只有一份报告.
    reports = (
        await session.execute(select(Report).where(Report.task_id == task.id))
    ).scalars().all()
    assert len(reports) == 1


@pytest.mark.asyncio
async def test_generation_job_commits_each_chapter_incrementally(db_session, monkeypatch):
    """后台 job 每章完成后立即写回 DB，前端轮询可看到渐进内容."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session, user = db_session
    task = await _seed_task(session, user.id)
    titles = chapter_titles()
    report = Report(
        task_id=task.id,
        review_id=None,
        format="markdown",
        content_path=f"report_chapters/task_{task.id}",
        status="generating",
    )
    session.add(report)
    await session.flush()
    for idx, title in enumerate(titles):
        session.add(
            ReportChapter(
                report_id=report.id,
                title=title,
                content="",
                order_index=idx,
            )
        )
    await session.commit()
    await session.refresh(report)
    report_id = report.id

    events = []

    async def _fake_build_chapter_content(
        db, task_obj, order_index, *, report_model=None, agg=None
    ):
        events.append(("build", order_index))
        return f"chapter-{order_index}"

    monkeypatch.setattr(
        "app.services.report_service_async.build_chapter_content",
        _fake_build_chapter_content,
    )
    monkeypatch.setattr(
        "app.services.report_service_async.async_session",
        async_sessionmaker(
            session.bind, class_=AsyncSession, expire_on_commit=False
        ),
    )
    original_commit = AsyncSession.commit

    async def _counting_commit(self):
        events.append(("commit", None))
        await original_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", _counting_commit)

    from app.services.report_service_async import ReportGenerationService

    service = ReportGenerationService()
    await service._run_generation_job(
        task_id=task.id,
        report_id=report_id,
        owner_id=user.id,
        report_model=None,
    )

    assert events[:16] == [
        item
        for idx in range(8)
        for item in (("build", idx), ("commit", None))
    ]
    assert events[16:] == [("commit", None)]
    session.expire_all()
    rows = (
        await session.execute(
            select(ReportChapter)
            .where(ReportChapter.report_id == report_id)
            .order_by(ReportChapter.order_index.asc())
        )
    ).scalars().all()
    assert [r.content for r in rows] == [f"chapter-{i}" for i in range(8)]
    row = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one()
    assert row.status == "generated"


@pytest.mark.asyncio
async def test_get_task_report_returns_chapters_and_annotations(client, db_session):
    """GET /tasks/{id}/report 取报告 + chapters（按 order_index 排序）+ annotations."""
    session, user = db_session
    task = await _seed_task(session, user.id)

    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)

    # 建一条批注挂第 0 章.
    chapter_id = generated.json()["chapters"][0]["id"]
    ann = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"chapter_id": chapter_id, "content": "请复核金额"},
    )
    assert ann.status_code == 200

    resp = await client.get(f"/api/tasks/{task.id}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == report_id
    assert [c["order_index"] for c in body["chapters"]] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["content"] == "请复核金额"
    assert body["annotations"][0]["author"] == "owner"


@pytest.mark.asyncio
async def test_get_task_report_404_when_not_generated(client, db_session):
    """未生成报告时 GET /tasks/{id}/report 返 404."""
    session, user = db_session
    task = await _seed_task(session, user.id)

    resp = await client.get(f"/api/tasks/{task.id}/report")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 章节编辑
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_chapter_updates_content(client, db_session):
    """PATCH 章节接口更新 content."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)
    chapter_id = generated.json()["chapters"][0]["id"]

    resp = await client.patch(
        f"/api/reports/{report_id}/chapters/{chapter_id}",
        json={"content": "## 概述\n\n人工修订后的正文。"},
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "## 概述\n\n人工修订后的正文。"

    # DB 真实更新.
    row = (
        await session.execute(
            select(ReportChapter).where(ReportChapter.id == chapter_id)
        )
    ).scalar_one()
    assert row.content == "## 概述\n\n人工修订后的正文。"


@pytest.mark.asyncio
async def test_patch_chapter_unknown_chapter_404(client, db_session):
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)

    resp = await client.patch(
        f"/api/reports/{report_id}/chapters/999999",
        json={"content": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generating_report_write_ops_return_409(client, db_session):
    """报告生成中禁止人工写操作，避免后台逐章写回覆盖人工编辑."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    chapter_id = generated.json()["chapters"][0]["id"]

    resp = await client.patch(
        f"/api/reports/{report_id}/chapters/{chapter_id}",
        json={"content": "x"},
    )
    assert resp.status_code == 409
    resp = await client.post(
        f"/api/reports/{report_id}/chapters/{chapter_id}/regenerate"
    )
    assert resp.status_code == 409
    resp = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"content": "x"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 单章重生成
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_chapter_rewrites_content(client, db_session):
    """单章重生成（mock agent run_chapter）重写 content，不改 title/order_index.

    06-28 Phase 2：走 build_one_chapter（agent.run + 模板兜底），mock agent 返
    固定 markdown。生成时是异步空章，重生成后填入 mock 内容。
    """
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)
    chapter = generated.json()["chapters"][0]

    # 先人工改掉 content.
    await client.patch(
        f"/api/reports/{report_id}/chapters/{chapter['id']}",
        json={"content": "人工临时内容"},
    )

    resp = await client.post(
        f"/api/reports/{report_id}/chapters/{chapter['id']}/regenerate"
    )
    assert resp.status_code == 200
    regenerated = resp.json()
    # mock agent 返 "## 概述\n\nLLM 生成的正文（mock）。".
    assert "LLM 生成的正文" in regenerated["content"]
    assert regenerated["title"] == chapter["title"]
    assert regenerated["order_index"] == chapter["order_index"]


# ---------------------------------------------------------------------------
# 拖拽排序
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reorder_chapters_updates_order_index(client, db_session):
    """reorder 批量更新 order_index."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)
    chapters = generated.json()["chapters"]

    # 把第 0 章和第 4 章交换 order_index.
    id0 = chapters[0]["id"]
    id4 = chapters[4]["id"]
    resp = await client.post(
        f"/api/reports/{report_id}/chapters/reorder",
        json=[
            {"chapter_id": id0, "order_index": 7},
            {"chapter_id": id4, "order_index": 0},
        ],
    )
    assert resp.status_code == 200
    new_chapters = resp.json()["chapters"]
    by_id = {c["id"]: c for c in new_chapters}
    assert by_id[id0]["order_index"] == 7
    assert by_id[id4]["order_index"] == 0


# ---------------------------------------------------------------------------
# 全报告重生成
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_report_rewrites_all_chapters(client, db_session):
    """全报告重生成：LLM 路径重写所有章节 content."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)
    chapter_id = generated.json()["chapters"][0]["id"]

    # 先改一章.
    await client.patch(
        f"/api/reports/{report_id}/chapters/{chapter_id}",
        json={"content": "人工内容"},
    )
    # 重生成全报告.
    resp = await client.post(f"/api/reports/{report_id}/regenerate")
    assert resp.status_code == 200
    ch0 = next(c for c in resp.json()["chapters"] if c["id"] == chapter_id)
    assert ch0["content"] != "人工内容"  # 被重生成覆盖
    assert "LLM 生成的正文" in ch0["content"]


# ---------------------------------------------------------------------------
# 批注增 + 切 resolved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_annotation_persists_with_author(client, db_session):
    """新建批注：author=current_user.username，resolved=false."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)
    chapter_id = generated.json()["chapters"][2]["id"]

    resp = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"chapter_id": chapter_id, "content": "数据范围需补充"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_id"] == report_id
    assert body["chapter_id"] == chapter_id
    assert body["author"] == "owner"
    assert body["resolved"] is False
    assert body["content"] == "数据范围需补充"


@pytest.mark.asyncio
async def test_toggle_annotation_flips_resolved(client, db_session):
    """PATCH 批注切换 resolved 状态."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)

    created = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"content": "待复核"},
    )
    ann_id = created.json()["id"]
    assert created.json()["resolved"] is False

    toggled = await client.patch(
        f"/api/reports/{report_id}/annotations/{ann_id}"
    )
    assert toggled.status_code == 200
    assert toggled.json()["resolved"] is True

    # DB 真实更新.
    row = (
        await session.execute(
            select(ReportAnnotation).where(ReportAnnotation.id == ann_id)
        )
    ).scalar_one()
    assert row.resolved is True


@pytest.mark.asyncio
async def test_create_annotation_unknown_chapter_404(client, db_session):
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)

    resp = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"chapter_id": 999999, "content": "x"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 定稿 + 定稿后写操作 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_report_sets_status_final(client, db_session):
    """POST /reports/{id}/finalize → status=final."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)

    resp = await client.post(f"/api/reports/{report_id}/finalize")
    assert resp.status_code == 200
    assert resp.json()["status"] == "final"

    # DB 真实更新.
    row = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one()
    assert row.status == "final"


@pytest.mark.asyncio
async def test_finalized_report_write_ops_return_409(client, db_session):
    """定稿后：编辑/单章重生成/reorder/全报告重生成/新建批注/切 resolved 均 409."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)
    chapter_id = generated.json()["chapters"][0]["id"]

    await client.post(f"/api/reports/{report_id}/finalize")

    # 编辑.
    r = await client.patch(
        f"/api/reports/{report_id}/chapters/{chapter_id}",
        json={"content": "x"},
    )
    assert r.status_code == 409
    # 单章重生成.
    r = await client.post(
        f"/api/reports/{report_id}/chapters/{chapter_id}/regenerate"
    )
    assert r.status_code == 409
    # reorder.
    r = await client.post(
        f"/api/reports/{report_id}/chapters/reorder",
        json=[{"chapter_id": chapter_id, "order_index": 7}],
    )
    assert r.status_code == 409
    # 全报告重生成.
    r = await client.post(f"/api/reports/{report_id}/regenerate")
    assert r.status_code == 409
    # 新建批注.
    r = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"content": "x"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_finalized_report_toggle_annotation_409(client, db_session):
    """定稿后切 resolved 返 409."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)

    created = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"content": "待复核"},
    )
    ann_id = created.json()["id"]

    await client.post(f"/api/reports/{report_id}/finalize")

    r = await client.patch(f"/api/reports/{report_id}/annotations/{ann_id}")
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# owner 校验 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_endpoints_owner_only_403(client, db_session):
    """非 owner 不能生成/取报告，也不能操作 report."""
    from app.models import Role, User

    session, user = db_session
    other_role = Role(name="other_reviewer")
    other = User(
        username="other",
        email="other@example.com",
        hashed_password="x",
        role=other_role,
        is_active=True,
    )
    task = await _seed_task(session, user.id)
    session.add_all([other_role, other])
    await session.commit()

    from app.auth.dependencies import get_current_user
    from app.main import app

    async def _other_user():
        return other

    app.dependency_overrides[get_current_user] = _other_user
    try:
        # 生成报告（非 owner）.
        r = await client.post(f"/api/tasks/{task.id}/report")
        assert r.status_code == 403
        # 取报告（非 owner）.
        r = await client.get(f"/api/tasks/{task.id}/report")
        assert r.status_code == 403
    finally:
        async def _owner():
            return user
        app.dependency_overrides[get_current_user] = _owner

    # owner 正常生成一份报告，再切回 other 验证 report 级 403.
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    await _mark_report_generated(session, report_id)
    chapter_id = generated.json()["chapters"][0]["id"]

    app.dependency_overrides[get_current_user] = _other_user
    try:
        r = await client.patch(
            f"/api/reports/{report_id}/chapters/{chapter_id}",
            json={"content": "x"},
        )
        assert r.status_code == 403
        r = await client.post(f"/api/reports/{report_id}/finalize")
        assert r.status_code == 403
        r = await client.post(
            f"/api/reports/{report_id}/annotations",
            json={"content": "x"},
        )
        assert r.status_code == 403
    finally:
        async def _owner():
            return user
        app.dependency_overrides[get_current_user] = _owner


@pytest.mark.asyncio
async def test_report_endpoints_unknown_report_404(client, db_session):
    """未知 report_id 返 404（owner 校验前先 404）."""
    session, user = db_session
    r = await client.post("/api/reports/999999/finalize")
    assert r.status_code == 404
    r = await client.patch(
        "/api/reports/999999/chapters/1",
        json={"content": "x"},
    )
    assert r.status_code == 404
