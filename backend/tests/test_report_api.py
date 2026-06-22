# -*- coding: utf-8 -*-
"""S7 审查报告闭环 API tests.

Covers (per prd §验证 新增后端单测):
* 报告生成建 6 章（幂等：重复生成返已有 draft 报告）.
* 章节编辑（PATCH content）.
* 单章重生成（占位确定性模板）.
* 拖拽排序（reorder）.
* 批注增 + 切 resolved.
* 定稿后写操作 409（编辑/重生成/reorder/新建批注/切 resolved）.
* owner 校验 403.
"""

import pytest
from sqlalchemy import select

from app.models import Report, ReportAnnotation, ReportChapter, Task


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


# ---------------------------------------------------------------------------
# 生成 6 章 + 幂等
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_report_creates_six_chapters(client, db_session):
    """POST /tasks/{id}/report 建 Report(status=draft) + 6 个 ReportChapter."""
    session, user = db_session
    task = await _seed_task(session, user.id)

    resp = await client.post(f"/api/tasks/{task.id}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == task.id
    assert body["status"] == "draft"
    assert body["review_id"] is None
    chapters = body["chapters"]
    assert len(chapters) == 6
    # 6 章固定标题 + order_index 0-5.
    assert [c["title"] for c in chapters] == [
        "概述", "被审查对象", "数据范围", "异常发现汇总", "风险评估", "结论建议",
    ]
    assert [c["order_index"] for c in chapters] == [0, 1, 2, 3, 4, 5]

    # DB 真实落 6 行 ReportChapter.
    rows = (
        await session.execute(
            select(ReportChapter).where(ReportChapter.report_id == body["id"])
        )
    ).scalars().all()
    assert len(rows) == 6

    # 概述章 content 含任务标题.
    overview = next(c for c in chapters if c["order_index"] == 0)
    assert task.title in overview["content"]


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
async def test_get_task_report_returns_chapters_and_annotations(client, db_session):
    """GET /tasks/{id}/report 取报告 + chapters（按 order_index 排序）+ annotations."""
    session, user = db_session
    task = await _seed_task(session, user.id)

    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]

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
    assert [c["order_index"] for c in body["chapters"]] == [0, 1, 2, 3, 4, 5]
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

    resp = await client.patch(
        f"/api/reports/{report_id}/chapters/999999",
        json={"content": "x"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 单章重生成
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_chapter_rewrites_content(client, db_session):
    """单章重生成（占位确定性模板）重写 content，不改 title/order_index."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
    chapter = generated.json()["chapters"][0]
    original = chapter["content"]

    # 先人工改掉 content，再重生成 → 应回到确定性模板.
    await client.patch(
        f"/api/reports/{report_id}/chapters/{chapter['id']}",
        json={"content": "人工临时内容"},
    )

    resp = await client.post(
        f"/api/reports/{report_id}/chapters/{chapter['id']}/regenerate"
    )
    assert resp.status_code == 200
    regenerated = resp.json()
    assert regenerated["content"] == original  # 回到确定性模板
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
    chapters = generated.json()["chapters"]

    # 把第 0 章和第 4 章交换 order_index.
    id0 = chapters[0]["id"]
    id4 = chapters[4]["id"]
    resp = await client.post(
        f"/api/reports/{report_id}/chapters/reorder",
        json=[
            {"chapter_id": id0, "order_index": 4},
            {"chapter_id": id4, "order_index": 0},
        ],
    )
    assert resp.status_code == 200
    new_chapters = resp.json()["chapters"]
    by_id = {c["id"]: c for c in new_chapters}
    assert by_id[id0]["order_index"] == 4
    assert by_id[id4]["order_index"] == 0


# ---------------------------------------------------------------------------
# 全报告重生成
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_report_rewrites_all_chapters(client, db_session):
    """全报告重生成：重新拼装所有章节 content（占位确定性）."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]
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
    assert task.title in ch0["content"]


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
        json=[{"chapter_id": chapter_id, "order_index": 5}],
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
    # 切 resolved（先在定稿前建一条批注，再定稿，再切）.
    created = await client.post(
        f"/api/reports/{report_id}/annotations",
        json={"content": "待复核"},
    )
    # 注意：上面新建批注被 409 拦了，所以这里需要先建再定稿。重置场景：
    # 重新建一个 task 走一遍 finalize-after-annotation.
    # 为保持本测试聚焦，单独在下一个测试覆盖 resolved-after-finalize.


@pytest.mark.asyncio
async def test_finalized_report_toggle_annotation_409(client, db_session):
    """定稿后切 resolved 返 409."""
    session, user = db_session
    task = await _seed_task(session, user.id)
    generated = await client.post(f"/api/tasks/{task.id}/report")
    report_id = generated.json()["id"]

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
