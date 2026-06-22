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
    task.status = "completed"
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
