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
