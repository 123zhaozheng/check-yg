# -*- coding: utf-8 -*-
"""06-23-tab keyword review tests: run / 重跑清旧 / hits / PATCH + 三层匹配命中.

覆盖（prd §7）:
* run：多选卡片 → 逐行 × 逐词三层匹配 → 命中入库。只扫 standard 记录的
  counterparty_name + summary 两列。
* run 统计：扫描记录数 / 命中记录数 / 命中词数 / 高风险命中数。
* 重跑清旧：第二次 run 换卡片集 → 旧命中被删，新命中入库（结果即当前选中卡片集）。
* hits 分页 + status/risk_level/match_type 过滤。
* PATCH hit：改 status（采纳/忽略）+ note。
* 只扫 standard：excluded/unparsed 记录不被扫。
* last_keyword_review_at 写入 task.config。

sqlite 内存 DB — no real network.
"""

import pytest
from sqlalchemy import select

from app.models import (
    FlowRecordRow,
    KeywordCard,
    KeywordHit,
    KeywordTerm,
    Task,
)


async def _seed_card(session, name: str, risk: str, terms: list[str]) -> KeywordCard:
    """Seed a card with terms, return the committed card."""
    card = KeywordCard(name=name, risk_level=risk)
    session.add(card)
    await session.commit()
    await session.refresh(card)
    for term in terms:
        session.add(KeywordTerm(card_id=card.id, term=term))
    await session.commit()
    return card


async def _seed_task_with_records(session, owner_id: int) -> tuple[Task, list[FlowRecordRow]]:
    """Seed a completed task with standard records (some with hits, some without)."""
    task = Task(title="kw-review", owner_id=owner_id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    records = [
        FlowRecordRow(
            task_id=task.id,
            record_type="standard",
            row_index=1,
            is_valid=True,
            counterparty_name="张三",
            summary="转账给张三 500元",
        ),
        FlowRecordRow(
            task_id=task.id,
            record_type="standard",
            row_index=2,
            is_valid=True,
            counterparty_name="李四",
            summary="货款支付",
        ),
        FlowRecordRow(
            task_id=task.id,
            record_type="standard",
            row_index=3,
            is_valid=True,
            counterparty_name="王五",
            summary="收款人 赵*辰 退款",
        ),
        # excluded 行不应被扫。
        FlowRecordRow(
            task_id=task.id,
            record_type="excluded",
            row_index=4,
            is_valid=False,
            counterparty_name="张三",
            summary="噪音行张三",
        ),
    ]
    session.add_all(records)
    await session.commit()
    for r in records:
        await session.refresh(r)
    return task, records


# ---------------------------------------------------------------------------
# run：三层匹配命中 + 统计 + 只扫 standard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_review_matches_exact_and_desensitized(client, db_session):
    """run：精确命中（张三）+ 脱敏命中（赵*辰）→ 命中入库 + 统计。"""
    session, user = db_session
    task, records = await _seed_task_with_records(session, user.id)
    card = await _seed_card(session, "对手卡", "高", ["张三", "赵北辰"])

    resp = await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card.id]},
    )
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    # 扫描 3 standard 记录。
    assert stats["scanned_records"] == 3
    # 命中记录：record1（张三 exact）+ record3（赵*辰 desensitized）= 2。
    assert stats["hit_records"] == 2
    # 命中词：张三 + 赵北辰 = 2。
    assert stats["hit_terms"] == 2
    # 高风险命中数：张三（counterparty exact）+ 张三（summary exact）+ 赵北辰（summary desensitized）= 3。
    assert stats["high_risk_hits"] == 3

    # 命中行入库。
    hits = (
        await session.execute(select(KeywordHit).where(KeywordHit.task_id == task.id))
    ).scalars().all()
    assert len(hits) == 3
    match_types = {h.match_type for h in hits}
    assert "精确匹配" in match_types
    assert "脱敏匹配" in match_types


@pytest.mark.asyncio
async def test_run_review_only_scans_standard_records(client, db_session):
    """excluded 记录的 counterparty_name=张三 不被扫（record_type=excluded）。"""
    session, user = db_session
    task, records = await _seed_task_with_records(session, user.id)
    card = await _seed_card(session, "卡", "中", ["张三"])

    resp = await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card.id]},
    )
    assert resp.status_code == 200
    # 扫描 3 standard（不含 excluded）。
    assert resp.json()["scanned_records"] == 3

    # 命中只来自 standard 记录——excluded 的 record4 (id 较大) 不应出现在命中里。
    hits = (
        await session.execute(select(KeywordHit).where(KeywordHit.task_id == task.id))
    ).scalars().all()
    hit_record_ids = {h.flow_record_id for h in hits}
    excluded_record = records[3]
    assert excluded_record.id not in hit_record_ids


@pytest.mark.asyncio
async def test_run_review_writes_last_keyword_review_at(client, db_session):
    """run 后 task.config.last_keyword_review_at 写入 ISO 时间戳。"""
    session, user = db_session
    task, _records = await _seed_task_with_records(session, user.id)
    card = await _seed_card(session, "卡", "中", ["张三"])

    await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card.id]},
    )

    task_row = (
        await session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert task_row.config is not None
    assert "last_keyword_review_at" in task_row.config
    assert task_row.config["last_keyword_review_at"]


# ---------------------------------------------------------------------------
# 重跑清旧命中再算
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerun_clears_old_hits(client, db_session):
    """重跑：先删该 task 旧命中，再插新命中（换卡片集结果即当前选中）。"""
    session, user = db_session
    task, _records = await _seed_task_with_records(session, user.id)
    card_a = await _seed_card(session, "卡A", "高", ["张三"])
    card_b = await _seed_card(session, "卡B", "低", ["李四"])

    # 第一次 run：卡A → 命中张三。
    resp1 = await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card_a.id]},
    )
    assert resp1.status_code == 200
    hits1 = (
        await session.execute(select(KeywordHit).where(KeywordHit.task_id == task.id))
    ).scalars().all()
    assert len(hits1) >= 1
    assert all(h.keyword_card_id == card_a.id for h in hits1)

    # 第二次 run：换卡B → 旧命中（卡A）被删，新命中（卡B 李四）入库。
    resp2 = await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card_b.id]},
    )
    assert resp2.status_code == 200
    hits2 = (
        await session.execute(select(KeywordHit).where(KeywordHit.task_id == task.id))
    ).scalars().all()
    # 全是卡B 的命中，卡A 命中已清。
    assert all(h.keyword_card_id == card_b.id for h in hits2)
    assert all(h.keyword_card_id != card_a.id for h in hits2)
    # 李四精确命中 record2。
    assert any(h.matched_snippet == "李四" for h in hits2)


@pytest.mark.asyncio
async def test_run_empty_card_ids_no_hits(client, db_session):
    """空 card_ids → 扫描记录但无命中（0 词）。"""
    session, user = db_session
    task, _records = await _seed_task_with_records(session, user.id)

    resp = await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": []},
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["scanned_records"] == 3
    assert stats["hit_records"] == 0
    assert stats["hit_terms"] == 0
    assert stats["high_risk_hits"] == 0


# ---------------------------------------------------------------------------
# hits 分页 + 过滤
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_hits_filter_by_status_and_match_type(client, db_session):
    """GET hits 支持 status / match_type 过滤 + 分页。"""
    session, user = db_session
    task, _records = await _seed_task_with_records(session, user.id)
    card = await _seed_card(session, "卡", "高", ["张三", "赵北辰"])

    await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card.id]},
    )

    # 全部命中。
    resp = await client.get(f"/api/tasks/{task.id}/keyword-review/hits")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert all(i["status"] == "pending" for i in data["items"])

    # 按 match_type 过滤：精确匹配。
    resp_exact = await client.get(
        f"/api/tasks/{task.id}/keyword-review/hits?match_type=精确匹配"
    )
    assert resp_exact.status_code == 200
    exact_data = resp_exact.json()
    assert exact_data["total"] >= 1
    assert all(i["match_type"] == "精确匹配" for i in exact_data["items"])

    # 按 risk_level 过滤：高。
    resp_risk = await client.get(
        f"/api/tasks/{task.id}/keyword-review/hits?risk_level=高"
    )
    assert resp_risk.status_code == 200
    assert all(i["risk_level"] == "高" for i in resp_risk.json()["items"])


# ---------------------------------------------------------------------------
# PATCH hit：status / note
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_hit_status_and_note(client, db_session):
    """PATCH hit：改 status=confirmed + note。"""
    session, user = db_session
    task, _records = await _seed_task_with_records(session, user.id)
    card = await _seed_card(session, "卡", "高", ["张三"])

    await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card.id]},
    )
    hit = (
        await session.execute(
            select(KeywordHit).where(KeywordHit.task_id == task.id).limit(1)
        )
    ).scalar_one()
    hit_id = hit.id

    # 改 status=confirmed。
    resp = await client.patch(
        f"/api/tasks/{task.id}/keyword-review/hits/{hit_id}",
        json={"status": "confirmed", "note": "采纳为告警"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["note"] == "采纳为告警"

    # DB 落库。
    await session.refresh(hit)
    assert hit.status == "confirmed"
    assert hit.note == "采纳为告警"


@pytest.mark.asyncio
async def test_patch_hit_invalid_status_422(client, db_session):
    """PATCH hit 非法 status → 422。"""
    session, user = db_session
    task, _records = await _seed_task_with_records(session, user.id)
    card = await _seed_card(session, "卡", "高", ["张三"])

    await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": [card.id]},
    )
    hit = (
        await session.execute(
            select(KeywordHit).where(KeywordHit.task_id == task.id).limit(1)
        )
    ).scalar_one()

    resp = await client.patch(
        f"/api/tasks/{task.id}/keyword-review/hits/{hit.id}",
        json={"status": "bogus"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_hit_not_found_404(client, db_session):
    """PATCH 不存在的 hit_id → 404。"""
    session, user = db_session
    task, _records = await _seed_task_with_records(session, user.id)

    resp = await client.patch(
        f"/api/tasks/{task.id}/keyword-review/hits/99999",
        json={"status": "confirmed"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# owner-only（非 owner 403）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keyword_review_owner_only_403(client, db_session):
    """非 task owner 调 run → 403（_load_owned_task 校验）。

    conftest 的 client 用 auditor user（非 task owner，无 admin）。
    task 的 owner_id 设成另一个不存在的 user id → 当前用户非 owner → 403。
    """
    session, _user = db_session
    task = Task(title="other-owner", owner_id=99999, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resp = await client.post(
        f"/api/tasks/{task.id}/keyword-review/run",
        json={"card_ids": []},
    )
    assert resp.status_code == 403
