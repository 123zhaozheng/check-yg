# -*- coding: utf-8 -*-
"""Review-fix tests: browser upload, path-aware document identity, single MinerU fetch."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Task
from app.services.extraction.runner import ExtractionTaskRunner


def _pdf_bytes(name: str = "sample.pdf") -> bytes:
    return b"%PDF-1.4\n% fake pdf body\n"


# ---------------------------------------------------------------------------
# Browser file upload (replaces backend-local directory input)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_from_upload_does_not_auto_start(client, monkeypatch):
    """Upload no longer auto-starts extraction (③ 手动处理).

    The task stays ``draft``, ``runner.start`` is NOT called, files are saved
    under a per-task run dir, and ``config.document_folder`` points at it.
    Extraction is started manually via POST /tasks/{id}/start.
    """
    calls = []

    async def fake_start(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    response = await client.post(
        "/api/tasks/upload",
        data={"title": "Upload task", "batch_size": "5", "confidence_threshold": "88"},
        files=[("files", ("流水.pdf", _pdf_bytes(), "application/pdf"))],
    )

    assert response.status_code == 201
    data = response.json()
    # Stays draft — no auto-start.
    assert data["status"] == "draft"
    assert calls == []
    # The document_folder points at the saved upload dir, not a user-typed path.
    folder = data["config"]["document_folder"]
    assert "tasks" in folder and "run-1" in folder
    assert Path(folder).exists()
    assert (Path(folder) / "流水.pdf").exists()


@pytest.mark.asyncio
async def test_create_from_upload_rejects_unsupported_files(client, monkeypatch):
    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    response = await client.post(
        "/api/tasks/upload",
        data={"title": "Bad upload"},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_append_from_upload_uses_distinct_run_dir(client, db_session, monkeypatch):
    """A second append upload lands in run-2/, distinct from run-1/, so a
    same-named file stays a distinct document (path-aware identity).

    ③ 手动处理: append-upload no longer calls runner.start; it just registers
    the folder. The run dir + append_document_folders are still tracked.
    """
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Appendable"},
        files=[("files", ("流水.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]
    run1 = created.json()["config"]["document_folder"]
    assert run1.endswith("run-1")

    # No auto-start → status stays draft (no reset needed between requests).
    append_resp = await client.post(
        f"/api/tasks/{task_id}/append-upload",
        files=[("files", ("流水.pdf", _pdf_bytes(), "application/pdf"))],
    )

    assert append_resp.status_code == 200
    run2 = append_resp.json()["config"]["append_document_folder"]
    assert run2.endswith("run-2")
    assert run1 != run2
    append_folders = append_resp.json()["config"]["append_document_folders"]
    assert append_folders == [run2]


# ---------------------------------------------------------------------------
# Path-aware checkpoint identity (P1-b)
# ---------------------------------------------------------------------------


def test_checkpoint_distinct_for_same_name_different_path(tmp_path):
    from app.services.extraction.checkpoint import CheckpointManager

    cm = CheckpointManager(base_dir=str(tmp_path))
    task_id = "t1"
    cm.save_checkpoint(task_id, "流水.pdf", {"status": "completed"}, document_path="D:/old/流水.pdf")
    cm.save_checkpoint(task_id, "流水.pdf", {"status": "completed"}, document_path="D:/new/流水.pdf")

    assert len(cm.list_task_checkpoints(task_id)) == 2
    assert cm.load_checkpoint(task_id, "流水.pdf", document_path="D:/old/流水.pdf")["status"] == "completed"
    assert cm.load_checkpoint(task_id, "流水.pdf", document_path="D:/new/流水.pdf")["status"] == "completed"
    # Without a path, no checkpoint is found (path-aware keying).
    assert cm.load_checkpoint(task_id, "流水.pdf") is None


def test_checkpoint_name_only_backwards_compatible(tmp_path):
    from app.services.extraction.checkpoint import CheckpointManager

    cm = CheckpointManager(base_dir=str(tmp_path))
    cm.save_checkpoint("t1", "doc.xlsx", {"status": "stage1_done"})
    assert cm.load_checkpoint("t1", "doc.xlsx")["status"] == "stage1_done"


# ---------------------------------------------------------------------------
# Single MinerU fetch per stage-1 pass (P2-a)
# ---------------------------------------------------------------------------


def test_pdf_parser_tables_and_context_single_mineru_fetch(tmp_path, monkeypatch):
    """extract_tables_and_context must call _get_markdown exactly once."""
    from app.parsers.pdf_parser import PDFParser, PDFDecryptor

    pdf_path = tmp_path / "stmt.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    calls = {"count": 0}

    def fake_get_markdown(path):
        calls["count"] += 1
        return (
            "账户说明文字\n"
            "<table><tr><th>日期</th><th>金额</th></tr>"
            "<tr><td>2024-01</td><td>-100</td></tr></table>"
        )

    monkeypatch.setattr(PDFDecryptor, "is_encrypted", staticmethod(lambda path: False))
    parser = PDFParser()
    monkeypatch.setattr(parser.client, "get_markdown", fake_get_markdown)

    tables, context = parser.extract_tables_and_context(pdf_path)

    assert calls["count"] == 1
    assert len(tables) == 1
    assert tables[0].rows[0] == ["日期", "金额"]
    assert "<table" not in context
    assert "账户说明文字" in context


# ---------------------------------------------------------------------------
# Append skips already-processed documents by full path (P1-b)
# ---------------------------------------------------------------------------


def test_extract_flows_append_skips_already_processed_paths(tmp_path, monkeypatch):
    """extract_flows_append filters documents already in processed_document_paths."""
    import asyncio
    from app.services.extraction.extractor import FlowExtractor, ExtractionResult
    from app.services.extraction.scanner import DocumentScanner

    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    (old_dir / "a.pdf").write_bytes(b"%PDF-1.4")
    (new_dir / "a.pdf").write_bytes(b"%PDF-1.4")
    (new_dir / "b.pdf").write_bytes(b"%PDF-1.4")

    extractor = FlowExtractor()
    real_scan = DocumentScanner.scan_directory

    def spy_scan(self, directory, recursive=True):
        return real_scan(self, directory, recursive)

    monkeypatch.setattr(DocumentScanner, "scan_directory", spy_scan)

    captured = {}

    async def fake_extract_flows(self, document_folder, task_id=None, batch_size=20,
                                 confidence_threshold=70, documents=None,
                                 mineru_concurrency=1, llm_concurrency=2):
        captured["documents"] = documents
        return ExtractionResult(task_id=task_id or "t", document_folder=document_folder)

    monkeypatch.setattr(FlowExtractor, "extract_flows", fake_extract_flows)

    # new_dir/a.pdf was already processed in a prior run; new_dir/b.pdf is new.
    # old_dir/a.pdf is a different path and would NOT be skipped (distinct doc).
    existing = [str(new_dir / "a.pdf")]
    asyncio.run(
        extractor.extract_flows_append(
            task_id="t1",
            new_folder=str(new_dir),
            existing_document_paths=existing,
        )
    )

    names = sorted(Path(d).name for d in captured["documents"])
    assert names == ["b.pdf"]
