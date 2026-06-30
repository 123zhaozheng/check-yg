# -*- coding: utf-8 -*-
"""Task extraction API contract tests."""

import pytest
from sqlalchemy import select

from app.models import Document, Task
from app.services.extraction.runner import ExtractionTaskRunner


@pytest.mark.asyncio
async def test_create_task_persists_draft(client):
    response = await client.post(
        "/api/tasks/",
        json={
            "title": "June audit",
            "description": "integration test",
            "document_folder": "D:/docs",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "June audit"
    assert data["status"] == "draft"
    assert data["config"]["document_folder"] == "D:/docs"


@pytest.mark.asyncio
async def test_create_task_persists_employee_and_archive_fields(client):
    """The new-task dialog writes employee + period + channels into the row."""
    response = await client.post(
        "/api/tasks/",
        json={
            "title": "2026 张三审查",
            "employee_name": "张三",
            "employee_id": "ZS-0421",
            "department": "财务部",
            "audit_start": "2026-01-01T00:00:00",
            "audit_end": "2026-06-30T00:00:00",
            "expected_channels": ["银行", "支付"],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["employee_name"] == "张三"
    assert data["employee_id"] == "ZS-0421"
    assert data["department"] == "财务部"
    assert data["audit_start"].startswith("2026-01-01")
    assert data["expected_channels"] == ["银行", "支付"]
    assert data["archived"] is False


@pytest.mark.asyncio
async def test_archive_unarchive_and_soft_delete(client):
    created = await client.post("/api/tasks/", json={"title": "To archive"})
    task_id = created.json()["id"]

    archive_resp = await client.post(f"/api/tasks/{task_id}/archive")
    assert archive_resp.status_code == 200
    assert archive_resp.json()["archived"] is True

    # Archived tasks are hidden from the default list.
    listed = await client.get("/api/tasks/")
    assert all(item["id"] != task_id for item in listed.json()["items"])

    # Asking explicitly for archived surfaces it.
    archived_list = await client.get("/api/tasks/?archived=true")
    assert any(item["id"] == task_id for item in archived_list.json()["items"])

    unarchive_resp = await client.post(f"/api/tasks/{task_id}/unarchive")
    assert unarchive_resp.status_code == 200
    assert unarchive_resp.json()["archived"] is False

    # Soft delete = archive (no row removal).
    delete_resp = await client.delete(f"/api/tasks/{task_id}")
    assert delete_resp.status_code == 204
    still_there = await client.get(f"/api/tasks/{task_id}")
    assert still_there.status_code == 200
    assert still_there.json()["archived"] is True


@pytest.mark.asyncio
async def test_list_filters_by_employee_id_and_search(client):
    await client.post(
        "/api/tasks/",
        json={"title": "Alpha audit", "employee_id": "EMP-001"},
    )
    await client.post(
        "/api/tasks/",
        json={"title": "Beta audit", "employee_id": "EMP-002"},
    )

    by_employee = await client.get("/api/tasks/?employee_id=EMP-001")
    assert by_employee.status_code == 200
    items = by_employee.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Alpha audit"

    by_search = await client.get("/api/tasks/?search=Beta")
    search_items = by_search.json()["items"]
    assert len(search_items) == 1
    assert search_items[0]["title"] == "Beta audit"


@pytest.mark.asyncio
async def test_list_search_matches_title_or_employee(client):
    """全局 search 同时匹配 任务名 OR 员工姓名 OR 员工工号。"""
    await client.post(
        "/api/tasks/",
        json={"title": "2026 张三审查", "employee_name": "张三", "employee_id": "ZS-0421"},
    )
    await client.post(
        "/api/tasks/",
        json={"title": "Beta audit", "employee_name": "李四", "employee_id": "LS-0888"},
    )
    await client.post(
        "/api/tasks/",
        json={"title": "Gamma audit", "employee_name": "王五", "employee_id": "WW-9999"},
    )

    # 命中 title。
    by_title = await client.get("/api/tasks/?search=Beta")
    titles = [item["title"] for item in by_title.json()["items"]]
    assert titles == ["Beta audit"]

    # 命中 employee_name（张三）。
    by_name = await client.get("/api/tasks/?search=张三")
    titles = [item["title"] for item in by_name.json()["items"]]
    assert titles == ["2026 张三审查"]

    # 命中 employee_id（LS-0888）。
    by_id = await client.get("/api/tasks/?search=LS-0888")
    titles = [item["title"] for item in by_id.json()["items"]]
    assert titles == ["Beta audit"]

    # 一个关键词同时命中多个字段维度（「张」既出现在 title 又出现在 employee_name）。
    broad = await client.get("/api/tasks/?search=张")
    titles = {item["title"] for item in broad.json()["items"]}
    # 只有一条任务 title/employee_name 含「张」，去重后应只有一条（不会重复返回）。
    assert titles == {"2026 张三审查"}

    # 不匹配时返回空。
    none_resp = await client.get("/api/tasks/?search=NOPE-XYZ")
    assert none_resp.json()["items"] == []

    # employee_id 精确查询参数仍按精确匹配工作（不被 search 的 OR 改动）。
    by_employee = await client.get("/api/tasks/?employee_id=WW-9999")
    titles = [item["title"] for item in by_employee.json()["items"]]
    assert titles == ["Gamma audit"]


@pytest.mark.asyncio
async def test_start_task_requires_existing_folder(client):
    created = await client.post("/api/tasks/", json={"title": "Needs folder"})
    task_id = created.json()["id"]

    response = await client.post(
        f"/api/tasks/{task_id}/start",
        json={"document_folder": "Z:/missing-folder"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_start_task_marks_running_and_dispatches_runner(client, tmp_path, monkeypatch):
    calls = []

    async def fake_start(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post("/api/tasks/", json={"title": "Runnable"})
    task_id = created.json()["id"]

    response = await client.post(
        f"/api/tasks/{task_id}/start",
        json={"document_folder": str(tmp_path), "batch_size": 5, "confidence_threshold": 88},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["config"]["batch_size"] == 5
    assert calls[0]["task_id"] == task_id
    assert calls[0]["document_folder"] == str(tmp_path)
    assert calls[0]["confidence_threshold"] == 88


@pytest.mark.asyncio
async def test_pause_resume_cancel_delegate_to_runner(client, monkeypatch):
    paused = []
    resumed = []
    cancelled = []

    async def fake_pause(task_id):
        paused.append(task_id)
        return True

    async def fake_resume(task_id):
        resumed.append(task_id)
        return True

    async def fake_cancel(task_id):
        cancelled.append(task_id)
        return True

    monkeypatch.setattr("app.routers.tasks.runner.pause", fake_pause)
    monkeypatch.setattr("app.routers.tasks.runner.resume", fake_resume)
    monkeypatch.setattr("app.routers.tasks.runner.cancel", fake_cancel)

    created = await client.post("/api/tasks/", json={"title": "Controls"})
    task_id = created.json()["id"]

    pause_response = await client.post(f"/api/tasks/{task_id}/pause")
    resume_response = await client.post(f"/api/tasks/{task_id}/resume")
    cancel_response = await client.post(f"/api/tasks/{task_id}/cancel")

    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "running"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert paused == [task_id]
    assert resumed == [task_id]
    assert cancelled == [task_id]


def test_append_result_merge_preserves_previous_records():
    previous = {
        "total_documents": 1,
        "processed_documents": 1,
        "total_tables": 2,
        "flow_tables": 1,
        "total_records": 1,
        "flow_records": [{"source_file": "old.xlsx"}],
        "failed_documents": [],
        "errors": [],
        "per_document_stats": {"old.xlsx": {"record_count": 1}},
    }
    current = {
        "task_time": "2026-06-16T00:00:00",
        "document_folder": "D:/new",
        "total_documents": 2,
        "processed_documents": 2,
        "total_tables": 3,
        "flow_tables": 2,
        "total_records": 2,
        "flow_records": [{"source_file": "new-a.xlsx"}, {"source_file": "new-b.xlsx"}],
        "failed_documents": ["bad.pdf"],
        "errors": [{"document": "bad.pdf", "stage": "stage1", "error": "x"}],
        "per_document_stats": {"new-a.xlsx": {"record_count": 1}},
    }

    merged = ExtractionTaskRunner._merge_results(previous, current)

    assert merged["total_documents"] == 3
    assert merged["processed_documents"] == 3
    assert merged["total_tables"] == 5
    assert merged["flow_tables"] == 3
    assert merged["total_records"] == 3
    assert [item["source_file"] for item in merged["flow_records"]] == [
        "old.xlsx",
        "new-a.xlsx",
        "new-b.xlsx",
    ]
    assert merged["failed_documents"] == ["bad.pdf"]
    assert merged["per_document_stats"]["old.xlsx"]["record_count"] == 1
    assert merged["append_runs"][0]["document_folder"] == "D:/new"


def test_append_merge_keeps_same_name_different_path_and_accumulates_paths():
    """Document identity is the full path, not the filename.

    Same-named files in different folders are distinct documents and both
    records are kept. processed_document_paths accumulates (deduped by path).
    Previous per_document_stats are preserved.
    """
    previous = {
        "total_documents": 1,
        "processed_documents": 1,
        "total_tables": 1,
        "flow_tables": 1,
        "total_records": 1,
        "flow_records": [{"source_file": "流水.pdf", "amount": "100"}],
        "failed_documents": ["流水.pdf"],
        "errors": [],
        "per_document_stats": {"流水.pdf": {"record_count": 1}},
        "processed_document_paths": ["D:/old/流水.pdf"],
    }
    # Append run: a NEW folder containing a same-named file (distinct path)
    # plus the exact same path already processed (which the append stage would
    # have filtered out, so it does not appear in current records).
    current = {
        "task_time": "2026-06-17T00:00:00",
        "document_folder": "D:/new",
        "total_documents": 1,
        "processed_documents": 1,
        "total_tables": 1,
        "flow_tables": 1,
        "total_records": 1,
        "flow_records": [
            {"source_file": "流水.pdf", "amount": "999"},  # same name, different folder
        ],
        "failed_documents": [],
        "errors": [],
        "per_document_stats": {"流水.pdf": {"record_count": 1}},
        "processed_document_paths": ["D:/new/流水.pdf"],
    }

    merged = ExtractionTaskRunner._merge_results(previous, current)

    # Both same-named records kept (path-based identity, not source_file dedup).
    amounts = [item["amount"] for item in merged["flow_records"]]
    assert amounts == ["100", "999"]
    assert merged["total_records"] == 2
    # processed_document_paths accumulates both distinct paths.
    assert merged["processed_document_paths"] == ["D:/old/流水.pdf", "D:/new/流水.pdf"]
    # Previous per_document_stats preserved (not overwritten by current).
    assert merged["per_document_stats"]["流水.pdf"]["record_count"] == 1
    # failed_documents deduped by name.
    assert merged["failed_documents"] == ["流水.pdf"]
    # append_runs accumulates.
    assert merged["append_runs"][0]["document_folder"] == "D:/new"


@pytest.mark.asyncio
async def test_append_task_records_all_folders_in_config(client, db_session, tmp_path, monkeypatch):
    """Each append must accumulate the folder into append_document_folders, not overwrite."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post("/api/tasks/", json={"title": "Append folders"})
    task_id = created.json()["id"]

    folder_a = tmp_path / "a"
    folder_b = tmp_path / "b"
    folder_a.mkdir()
    folder_b.mkdir()

    # First append.
    await client.post(f"/api/tasks/{task_id}/append", json={"document_folder": str(folder_a)})

    # The router flips status to "running" and fake_start never finishes it;
    # reset via the test session so the second append is accepted.
    from app.models import Task as TaskModel
    from sqlalchemy import select

    row = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = row.scalar_one()
    task.status = "analyzing"
    await session.commit()

    resp = await client.post(f"/api/tasks/{task_id}/append", json={"document_folder": str(folder_b)})

    assert resp.status_code == 200
    folders = resp.json()["config"]["append_document_folders"]
    assert folders == [str(folder_a), str(folder_b)]


@pytest.mark.asyncio
async def test_runner_persists_result_records_for_review_services(db_session):
    session, user = db_session
    task = Task(title="Persist records", owner_id=user.id, status="running")
    session.add(task)
    await session.commit()
    await session.refresh(task)

    result = {
        "flow_records": [
            {
                "source_file": "a.xlsx",
                "original_row": "2",
                "transaction_time": "2026-06-17 10:00:00",
                "counterparty_name": "张三",
                "amount": "100.00",
            },
            {
                "source_file": "b.xlsx",
                "original_row": "3",
                "transaction_time": "2026-06-17 11:00:00",
                "counterparty_name": "李四",
                "amount": "200.00",
            },
        ],
        "failed_documents": [],
        "errors": [],
        "total_records": 2,
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    docs = (
        await session.execute(select(Document).where(Document.task_id == task.id).order_by(Document.filename.asc()))
    ).scalars().all()
    assert [doc.filename for doc in docs] == ["a.xlsx", "b.xlsx"]
    assert docs[0].flow_tables["records"][0]["counterparty_name"] == "张三"


# ---------------------------------------------------------------------------
# S4 data import — channel persistence, documents list, soft delete.
# ---------------------------------------------------------------------------


def _pdf_bytes(name: str = "sample.pdf") -> bytes:
    return b"%PDF-1.4\n% fake pdf body\n"


@pytest.mark.asyncio
async def test_append_upload_persists_channel_on_documents(client, db_session, monkeypatch):
    """Uploading with a channel labels every pre-created Document row."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Channel task", "channel": "银行流水"},
        files=[
            ("files", ("a.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("b.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    docs = (
        await session.execute(
            select(Document).where(Document.task_id == task_id).order_by(Document.filename.asc())
        )
    ).scalars().all()
    assert [d.filename for d in docs] == ["a.pdf", "b.pdf"]
    assert all(d.channel == "银行流水" for d in docs)
    assert all(d.status == "pending" for d in docs)
    # size_bytes captured at upload.
    assert all(d.size_bytes is not None and d.size_bytes > 0 for d in docs)


@pytest.mark.asyncio
async def test_runner_persist_updates_precreated_rows_preserving_channel(db_session):
    """_persist_result_documents updates pre-created rows in place (no delete+rebuild).

    Channel + size_bytes from the pre-created row are preserved; only flow_tables
    and status flip to completed.
    """
    session, user = db_session
    task = Task(title="Persist with channel", owner_id=user.id, status="running")
    session.add(task)
    await session.flush()

    pre = Document(
        task_id=task.id,
        filename="a.xlsx",
        original_path="/tmp/run-1/a.xlsx",
        status="pending",
        channel="支付渠道",
        size_bytes=123,
    )
    session.add(pre)
    await session.commit()
    await session.refresh(task)
    pre_id = pre.id

    result = {
        "flow_records": [
            {
                "source_file": "a.xlsx",
                "original_row": "2",
                "transaction_time": "2026-06-17 10:00:00",
                "counterparty_name": "张三",
                "amount": "100.00",
            },
        ],
        "failed_documents": [],
        "errors": [],
        "total_records": 1,
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    docs = (
        await session.execute(select(Document).where(Document.task_id == task.id))
    ).scalars().all()
    # Same row updated in place — no new row, id preserved.
    assert len(docs) == 1
    assert docs[0].id == pre_id
    assert docs[0].status == "completed"
    assert docs[0].channel == "支付渠道"
    assert docs[0].size_bytes == 123
    assert docs[0].flow_tables["records"][0]["counterparty_name"] == "张三"


@pytest.mark.asyncio
async def test_runner_persist_marks_failed_documents(db_session):
    """A pre-created row whose filename is in failed_documents flips to failed."""
    session, user = db_session
    task = Task(title="Failed doc", owner_id=user.id, status="running")
    session.add(task)
    await session.flush()

    pre = Document(
        task_id=task.id,
        filename="bad.pdf",
        original_path="/tmp/run-1/bad.pdf",
        status="pending",
        channel="银行流水",
        size_bytes=10,
    )
    session.add(pre)
    await session.commit()
    await session.refresh(task)

    result = {
        "flow_records": [],
        "failed_documents": ["bad.pdf"],
        "errors": [{"document": "bad.pdf", "stage": "stage1", "error": "parse boom"}],
        "total_records": 0,
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    doc = (
        await session.execute(select(Document).where(Document.task_id == task.id))
    ).scalar_one()
    assert doc.status == "failed"
    assert doc.error_log == "parse boom"
    # Channel preserved across failure.
    assert doc.channel == "银行流水"


@pytest.mark.asyncio
async def test_runner_persist_never_touches_soft_deleted_rows(db_session):
    """A status=deleted row is never matched/updated — 不删减 hard line."""
    session, user = db_session
    task = Task(title="Soft deleted", owner_id=user.id, status="running")
    session.add(task)
    await session.flush()

    deleted = Document(
        task_id=task.id,
        filename="a.xlsx",
        original_path="/tmp/run-1/a.xlsx",
        status="deleted",
        channel="银行流水",
        size_bytes=5,
    )
    pending = Document(
        task_id=task.id,
        filename="a.xlsx",
        original_path="/tmp/run-2/a.xlsx",
        status="pending",
        channel="支付渠道",
        size_bytes=9,
    )
    session.add_all([deleted, pending])
    await session.commit()
    await session.refresh(task)

    result = {
        "flow_records": [{"source_file": "a.xlsx", "amount": "1"}],
        "failed_documents": [],
        "errors": [],
        "total_records": 1,
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    docs = (
        await session.execute(
            select(Document).where(Document.task_id == task.id).order_by(Document.id.asc())
        )
    ).scalars().all()
    assert len(docs) == 2
    # The deleted row stays deleted (untouched); the pending row is consumed.
    statuses = {d.id: d.status for d in docs}
    assert statuses[deleted.id] == "deleted"
    assert statuses[pending.id] == "completed"


@pytest.mark.asyncio
async def test_runner_persist_marks_no_record_docs_completed(db_session):
    """A pre-created row whose doc produced no flow records flips to completed.

    Documents processed by the extractor but yielding no flow_records (e.g. a
    PDF with no extractable tables, or a portrait-only doc) have no entry in
    flow_records or failed_documents. Without a final sweep, their pre-created
    row would stay "pending" forever and the import page would poll
    indefinitely. The runner must mark them completed with empty flow_tables.
    """
    session, user = db_session
    task = Task(title="No records", owner_id=user.id, status="running")
    session.add(task)
    await session.flush()

    pre = Document(
        task_id=task.id,
        filename="empty.pdf",
        original_path="/tmp/run-1/empty.pdf",
        status="pending",
        channel="银行流水",
        size_bytes=42,
    )
    session.add(pre)
    await session.commit()
    await session.refresh(task)
    pre_id = pre.id

    # Extraction finished with zero flow_records and empty failed_documents —
    # the doc was processed but yielded nothing.
    result = {
        "flow_records": [],
        "failed_documents": [],
        "errors": [],
        "total_records": 0,
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    doc = (
        await session.execute(select(Document).where(Document.id == pre_id))
    ).scalar_one()
    assert doc.status == "completed"
    assert doc.flow_tables == {"records": []}
    # Channel preserved across the no-record sweep.
    assert doc.channel == "银行流水"
    assert doc.size_bytes == 42


@pytest.mark.asyncio
async def test_list_documents_filters_by_channel(client, db_session, monkeypatch):
    """GET /documents?channel= filters to that channel only."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Two channels", "channel": "银行流水"},
        files=[("files", ("bank.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    # Reset task to completed so append-upload is accepted.
    row = await session.execute(select(Task).where(Task.id == task_id))
    task = row.scalar_one()
    task.status = "analyzing"
    await session.commit()

    await client.post(
        f"/api/tasks/{task_id}/append-upload",
        data={"channel": "支付渠道"},
        files=[("files", ("pay.pdf", _pdf_bytes(), "application/pdf"))],
    )

    all_docs = await client.get(f"/api/tasks/{task_id}/documents")
    assert all_docs.status_code == 200
    assert all_docs.json()["total"] == 2

    bank = await client.get(f"/api/tasks/{task_id}/documents?channel=银行流水")
    bank_items = bank.json()["items"]
    assert len(bank_items) == 1
    assert bank_items[0]["filename"] == "bank.pdf"
    assert bank_items[0]["channel"] == "银行流水"

    pay = await client.get(f"/api/tasks/{task_id}/documents?channel=支付渠道")
    pay_items = pay.json()["items"]
    assert len(pay_items) == 1
    assert pay_items[0]["filename"] == "pay.pdf"
    assert pay_items[0]["channel"] == "支付渠道"


@pytest.mark.asyncio
async def test_delete_document_soft_deletes_and_hides_from_default_list(client, db_session, monkeypatch):
    """DELETE /documents/{id} flips status to deleted; row stays; default list hides it."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Delete me", "channel": "银行流水"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    before = await client.get(f"/api/tasks/{task_id}/documents")
    doc_id = before.json()["items"][0]["id"]

    delete_resp = await client.delete(f"/api/tasks/{task_id}/documents/{doc_id}")
    assert delete_resp.status_code == 204

    # Row still exists in DB (soft delete, 不删减).
    row = await session.execute(select(Document).where(Document.id == doc_id))
    doc = row.scalar_one()
    assert doc.status == "deleted"

    # Default list hides deleted rows.
    default_list = await client.get(f"/api/tasks/{task_id}/documents")
    assert default_list.json()["total"] == 0
    assert all(d["id"] != doc_id for d in default_list.json()["items"])

    # include_deleted=true surfaces it.
    with_deleted = await client.get(
        f"/api/tasks/{task_id}/documents?include_deleted=true"
    )
    assert with_deleted.json()["total"] == 1
    assert with_deleted.json()["items"][0]["id"] == doc_id
    assert with_deleted.json()["items"][0]["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_document_unknown_id_returns_404(client, monkeypatch):
    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Exists"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    resp = await client.delete(f"/api/tasks/{task_id}/documents/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_append_upload_rejects_unsupported_files_regression(client, db_session, monkeypatch):
    """422 on no-supported-files is preserved after the channel refactor."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Regression"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    row = await session.execute(select(Task).where(Task.id == task_id))
    task = row.scalar_one()
    task.status = "analyzing"
    await session.commit()

    resp = await client.post(
        f"/api/tasks/{task_id}/append-upload",
        data={"channel": "银行流水"},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert resp.status_code == 422
