# -*- coding: utf-8 -*-
"""S5 清洗标准化 API contract tests — flow_records endpoints + cleaning commit/export.

Covers:
* GET /tasks/{id}/records (default standard, filter by record_type, channel, pagination)
* GET /tasks/{id}/records/{record_id} (single drill-down — 流水号弹窗)
* GET /tasks/{id}/excluded (excluded + unparsed, active only)
* POST /tasks/{id}/records/{record_id}/restore (status → restored, row stays)
* POST /tasks/{id}/cleaning/commit (writes cleaning_committed timestamp)
* GET /tasks/{id}/cleaning/export (CSV + JSON, raw_payload + exclude_reason)
* Owner-only (403 for non-owner — covered by _load_owned_task reuse).
"""

import pytest
from sqlalchemy import select

from app.models import FlowRecordRow, Task


async def _seed_records(session, task_id: int) -> dict[str, int]:
    """Seed a few flow_records rows for a task; return ids by label."""
    ids: dict[str, int] = {}
    rows = [
        FlowRecordRow(
            task_id=task_id,
            document_id=None,
            channel="银行流水",
            record_type="standard",
            row_index=1,
            is_valid=True,
            transaction_time="2026-06-17 10:00:00",
            counterparty_name="张三",
            amount="100.00",
            raw_amount="100.00",
            transaction_type="收入",
            summary="消费",
            raw_payload={"cells": ["2026-06-17", "张三", "100.00"]},
            status="active",
        ),
        FlowRecordRow(
            task_id=task_id,
            document_id=None,
            channel="银行流水",
            record_type="unparsed",
            row_index=2,
            is_valid=False,
            summary="合计",
            raw_payload={"cells": ["", "", "合计 250.00"]},
            status="active",
            exclude_reason="normalizer: noise row (is_valid=false)",
        ),
        FlowRecordRow(
            task_id=task_id,
            document_id=None,
            channel="支付渠道",
            record_type="excluded",
            row_index=1,
            is_valid=False,
            raw_payload={"cells": ["账户信息", "账号 6222****1234"]},
            status="active",
            exclude_reason="classifier: not flow table",
        ),
        FlowRecordRow(
            task_id=task_id,
            document_id=None,
            channel="支付渠道",
            record_type="standard",
            row_index=3,
            is_valid=True,
            transaction_time="2026-06-18 11:00:00",
            counterparty_name="李四",
            amount="200.00",
            raw_amount="-200.00",
            transaction_type="支出",
            raw_payload={"cells": ["2026-06-18", "李四", "200.00"]},
            status="active",
        ),
    ]
    session.add_all(rows)
    await session.commit()
    by_type = (await session.execute(
        select(FlowRecordRow).where(FlowRecordRow.task_id == task_id).order_by(FlowRecordRow.id.asc())
    )).scalars().all()
    ids["standard_1"] = by_type[0].id
    ids["unparsed"] = by_type[1].id
    ids["excluded"] = by_type[2].id
    ids["standard_2"] = by_type[3].id
    return ids


@pytest.mark.asyncio
async def test_list_records_defaults_to_standard(client, db_session):
    session, _user = db_session
    task = Task(title="Records", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    ids = await _seed_records(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/records")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2  # only the 2 standard rows
    returned_ids = {item["id"] for item in data["items"]}
    assert returned_ids == {ids["standard_1"], ids["standard_2"]}
    # RecordResponse carries raw_payload.
    first = data["items"][0]
    assert first["raw_payload"]["cells"] == ["2026-06-17", "张三", "100.00"]
    assert first["record_type"] == "standard"
    assert first["transaction_type"] == "收入"


@pytest.mark.asyncio
async def test_list_records_filter_by_record_type_all(client, db_session):
    session, _user = db_session
    task = Task(title="All records", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_records(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/records?record_type=all")
    assert resp.status_code == 200
    assert resp.json()["total"] == 4  # all rows


@pytest.mark.asyncio
async def test_list_records_filter_by_channel(client, db_session):
    session, _user = db_session
    task = Task(title="By channel", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_records(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/records?channel=支付渠道&record_type=all")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert all(item["channel"] == "支付渠道" for item in items)


@pytest.mark.asyncio
async def test_list_excluded_returns_only_active_excluded_and_unparsed(client, db_session):
    session, _user = db_session
    task = Task(title="Excluded view", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    ids = await _seed_records(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/excluded")
    assert resp.status_code == 200
    data = resp.json()
    # 1 unparsed + 1 excluded = 2; standard rows not in this view.
    assert data["total"] == 2
    returned_ids = {item["id"] for item in data["items"]}
    assert returned_ids == {ids["unparsed"], ids["excluded"]}
    for item in data["items"]:
        assert item["record_type"] in ("excluded", "unparsed")
        assert item["status"] == "active"


@pytest.mark.asyncio
async def test_list_excluded_filter_by_record_type_paginates_per_type(client, db_session):
    """record_type filter narrows the excluded view so sub-tabs paginate independently.

    Without this filter the frontend's 非流水表 / 噪音行 sub-tabs would paginate
    a mixed list client-side, showing empty slots when one type is sparse on a
    page. The filter keeps server-side pagination correct per type.
    """
    session, _user = db_session
    task = Task(title="Excluded per type", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    ids = await _seed_records(session, task.id)

    # Narrow to excluded only.
    resp_ex = await client.get(f"/api/tasks/{task.id}/excluded?record_type=excluded")
    assert resp_ex.status_code == 200
    ex_data = resp_ex.json()
    assert ex_data["total"] == 1
    assert ex_data["items"][0]["id"] == ids["excluded"]
    assert ex_data["items"][0]["record_type"] == "excluded"

    # Narrow to unparsed only.
    resp_un = await client.get(f"/api/tasks/{task.id}/excluded?record_type=unparsed")
    assert resp_un.status_code == 200
    un_data = resp_un.json()
    assert un_data["total"] == 1
    assert un_data["items"][0]["id"] == ids["unparsed"]
    assert un_data["items"][0]["record_type"] == "unparsed"

    # Bogus value falls back to both types (defensive — never 422).
    resp_bogus = await client.get(f"/api/tasks/{task.id}/excluded?record_type=standard")
    assert resp_bogus.status_code == 200
    assert resp_bogus.json()["total"] == 2


@pytest.mark.asyncio
async def test_restore_marks_row_restored_and_keeps_row(client, db_session):
    """POST /records/{id}/restore flips status to restored; row stays (不删减)."""
    session, _user = db_session
    task = Task(title="Restore", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    ids = await _seed_records(session, task.id)

    resp = await client.post(f"/api/tasks/{task.id}/records/{ids['excluded']}/restore")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restored"
    # record_type is NOT promoted to standard (this slice only marks restored).
    assert resp.json()["record_type"] == "excluded"

    # Row still exists in DB (不删减).
    row = (
        await session.execute(select(FlowRecordRow).where(FlowRecordRow.id == ids["excluded"]))
    ).scalar_one()
    assert row.status == "restored"
    assert row.record_type == "excluded"

    # Restored row drops out of the excluded view.
    excluded = await client.get(f"/api/tasks/{task.id}/excluded")
    assert all(item["id"] != ids["excluded"] for item in excluded.json()["items"])


@pytest.mark.asyncio
async def test_restore_unknown_record_returns_404(client, db_session):
    session, _user = db_session
    task = Task(title="No such record", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resp = await client.post(f"/api/tasks/{task.id}/records/999999/restore")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_single_record_returns_row_with_raw_payload(client, db_session):
    """GET /records/{id} returns the single row (流水号弹窗 drill-down)."""
    session, _user = db_session
    task = Task(title="Single record", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    ids = await _seed_records(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/records/{ids['standard_1']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == ids["standard_1"]
    assert data["record_type"] == "standard"
    assert data["raw_payload"]["cells"] == ["2026-06-17", "张三", "100.00"]
    # Any record_type is reachable by id (not just standard) — the dialog may
    # drill into excluded/unparsed rows too.
    resp_ex = await client.get(f"/api/tasks/{task.id}/records/{ids['excluded']}")
    assert resp_ex.status_code == 200
    assert resp_ex.json()["record_type"] == "excluded"


@pytest.mark.asyncio
async def test_get_single_record_unknown_returns_404(client, db_session):
    session, _user = db_session
    task = Task(title="Single 404", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resp = await client.get(f"/api/tasks/{task.id}/records/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_single_record_cross_task_id_pair_returns_404(client, db_session):
    """record_id from another task must not leak — the task_id+record_id pair
    filter blocks cross-task lookups even if the id exists elsewhere."""
    from app.models import Task as TaskModel

    session, _user = db_session
    task_a = TaskModel(title="Task A", owner_id=_user.id, status="completed")
    task_b = TaskModel(title="Task B", owner_id=_user.id, status="completed")
    session.add_all([task_a, task_b])
    await session.commit()
    await session.refresh(task_a)
    await session.refresh(task_b)
    ids_a = await _seed_records(session, task_a.id)

    # record belongs to task_a → asking via task_b must 404.
    resp = await client.get(f"/api/tasks/{task_b.id}/records/{ids_a['standard_1']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_commit_cleaning_writes_timestamp(client, db_session):
    session, _user = db_session
    task = Task(title="Commit", owner_id=_user.id, status="completed", config={})
    session.add(task)
    await session.commit()
    await session.refresh(task)

    resp = await client.post(f"/api/tasks/{task.id}/cleaning/commit")
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert "cleaning_committed" in config
    assert config["cleaning_committed"]  # ISO timestamp string


@pytest.mark.asyncio
async def test_export_cleaning_log_csv(client, db_session):
    session, _user = db_session
    task = Task(title="Export CSV", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_records(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/cleaning/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "attachment" in resp.headers.get("content-disposition", "")
    # Body is UTF-8-sig (BOM) — decode and check the header + excluded reason.
    body = resp.content.decode("utf-8-sig")
    header = body.splitlines()[0]
    assert "record_type" in header
    assert "source_file" in header
    assert "raw_payload" in header
    assert "classifier: not flow table" in body
    assert "normalizer: noise row" in body


@pytest.mark.asyncio
async def test_export_cleaning_log_csv_writes_document_filename(client, db_session):
    """CSV source_file column carries the linked Document.filename, not the id.

    Regression guard: the CSV header declares a ``source_file`` column; the row
    must write the document's filename (human-readable) rather than the opaque
    ``document_id`` integer. ``FlowRecordRow`` has no source_file column, so the
    export joins Document to resolve the name.
    """
    from app.models import Document

    session, _user = db_session
    task = Task(title="Export CSV filename", owner_id=_user.id, status="completed")
    session.add(task)
    await session.flush()

    doc = Document(
        task_id=task.id,
        filename="bank_statement.pdf",
        original_path="/tmp/bank_statement.pdf",
        status="completed",
        channel="银行流水",
    )
    session.add(doc)
    await session.flush()
    session.add(
        FlowRecordRow(
            task_id=task.id,
            document_id=doc.id,
            channel="银行流水",
            record_type="excluded",
            row_index=1,
            is_valid=False,
            raw_payload={"cells": ["x", "y"]},
            status="active",
            exclude_reason="classifier: not flow table",
        )
    )
    await session.commit()
    await session.refresh(task)

    resp = await client.get(f"/api/tasks/{task.id}/cleaning/export?format=csv")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")
    # The filename appears in the body, and the document_id integer does NOT
    # appear in the source_file column position (column 5 of each data row).
    assert "bank_statement.pdf" in body
    lines = body.splitlines()
    data_row = lines[1] if len(lines) > 1 else ""
    # Column 5 (source_file) is the filename, not the bare doc id.
    cols = data_row.split(",")
    assert cols[4] == "bank_statement.pdf"


@pytest.mark.asyncio
async def test_export_cleaning_log_json(client, db_session):
    session, _user = db_session
    task = Task(title="Export JSON", owner_id=_user.id, status="completed")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await _seed_records(session, task.id)

    resp = await client.get(f"/api/tasks/{task.id}/cleaning/export?format=json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    payload = resp.json()
    # Only excluded + unparsed rows are in the log (2 of the 4 seeded).
    assert len(payload) == 2
    types = {item["record_type"] for item in payload}
    assert types == {"excluded", "unparsed"}
    for item in payload:
        assert "raw_payload" in item
        assert "exclude_reason" in item


@pytest.mark.asyncio
async def test_records_endpoints_owner_only_403(client, db_session):
    """Non-owner cannot read/restore a task's records."""
    from app.models import Role, User

    session, _user = db_session
    # Create a second user; the client is auth'd as the first (conftest owner).
    other_role = Role(name="other_auditor")
    other = User(
        username="other",
        email="other@example.com",
        hashed_password="x",
        role=other_role,
        is_active=True,
    )
    task = Task(title="Mine", owner_id=_user.id, status="completed")
    session.add_all([other_role, other, task])
    await session.commit()
    await session.refresh(task)

    # Re-auth as the other user via dependency override.
    from app.auth.dependencies import get_current_user
    from app.main import app

    async def _other_user():
        return other

    app.dependency_overrides[get_current_user] = _other_user
    try:
        resp = await client.get(f"/api/tasks/{task.id}/records")
        assert resp.status_code == 403
        resp = await client.get(f"/api/tasks/{task.id}/excluded")
        assert resp.status_code == 403
        resp = await client.post(f"/api/tasks/{task.id}/cleaning/commit")
        assert resp.status_code == 403
    finally:
        # Restore the conftest override.
        async def _owner():
            return _user
        app.dependency_overrides[get_current_user] = _owner
