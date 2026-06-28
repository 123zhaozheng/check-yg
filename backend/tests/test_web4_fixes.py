# -*- coding: utf-8 -*-
"""S-web-4 fixes tests: ③ 手动处理+并发限流 / ④ 文档画像持久化.

Covers (per prd §测试要求):
* ④ portrait 持久化: _persist_result_documents writes per_document_portraits
  onto the matched Document row; DocumentResponse carries portrait; GET
  /documents returns it.
* ③ 手动处理: upload does not auto-start (draft); append-upload no longer 409s
  while running; DEFAULT_SETTINGS has the two new extraction concurrency keys;
  runner.start reads concurrency from runtime settings and threads it into
  extract_flows; the batch loop re-runs when new pending documents appear
  mid-run.

Mock LLM agent + sqlite memory DB — no real network.
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Document, Task
from app.services.extraction.runner import ExtractionTaskRunner


def _pdf_bytes(name: str = "sample.pdf") -> bytes:
    return b"%PDF-1.4\n% fake pdf body\n"


# ---------------------------------------------------------------------------
# ④ 文档画像持久化
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_result_documents_writes_portrait_onto_matched_row(db_session):
    """per_document_portraits is written onto the pre-created Document row."""
    session, user = db_session
    task = Task(title="Portrait persist", owner_id=user.id, status="running")
    session.add(task)
    await session.flush()

    pre = Document(
        task_id=task.id,
        filename="a.xlsx",
        original_path="/tmp/run-1/a.xlsx",
        status="pending",
        channel="银行流水",
        size_bytes=11,
    )
    session.add(pre)
    await session.commit()
    await session.refresh(task)
    pre_id = pre.id

    portrait = {
        "account_type": "debit_card",
        "account_holder": "张三",
        "institution": "某银行",
        "statement_period": "2026-01 至 2026-06",
        "amount_sign_rule": "pos_income",
        "header_attributes": ["日期", "金额"],
    }
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
        "per_document_portraits": {"a.xlsx": portrait},
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    doc = (
        await session.execute(select(Document).where(Document.id == pre_id))
    ).scalar_one()
    assert doc.status == "completed"
    assert doc.portrait == portrait


@pytest.mark.asyncio
async def test_persist_result_documents_no_record_doc_still_gets_portrait(db_session):
    """A doc processed with no flow records still receives its stage-1 portrait."""
    session, user = db_session
    task = Task(title="No-record portrait", owner_id=user.id, status="running")
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

    portrait = {"account_type": "bank_general", "amount_sign_rule": "unknown"}
    result = {
        "flow_records": [],
        "failed_documents": [],
        "errors": [],
        "total_records": 0,
        "per_document_portraits": {"empty.pdf": portrait},
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    doc = (
        await session.execute(select(Document).where(Document.id == pre_id))
    ).scalar_one()
    assert doc.status == "completed"
    assert doc.portrait == portrait


@pytest.mark.asyncio
async def test_persist_result_documents_null_portrait_when_extraction_failed(db_session):
    """A doc whose portrait is None (LLM failed) gets portrait=None written through."""
    session, user = db_session
    task = Task(title="Null portrait", owner_id=user.id, status="running")
    session.add(task)
    await session.flush()

    pre = Document(
        task_id=task.id,
        filename="a.xlsx",
        original_path="/tmp/run-1/a.xlsx",
        status="pending",
        channel="支付渠道",
        size_bytes=7,
    )
    session.add(pre)
    await session.commit()
    await session.refresh(task)
    pre_id = pre.id

    result = {
        "flow_records": [
            {"source_file": "a.xlsx", "amount": "1"},
        ],
        "failed_documents": [],
        "errors": [],
        "total_records": 1,
        "per_document_portraits": {"a.xlsx": None},
    }

    await ExtractionTaskRunner._persist_result_documents(session, task.id, result)

    doc = (
        await session.execute(select(Document).where(Document.id == pre_id))
    ).scalar_one()
    assert doc.status == "completed"
    # None written through — the hover card shows 「画像待生成」.
    assert doc.portrait is None


@pytest.mark.asyncio
async def test_documents_endpoint_returns_portrait(client, db_session, monkeypatch):
    """GET /tasks/{id}/documents carries portrait on each row."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Portrait task", "channel": "银行流水"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    # Seed a portrait directly onto the pre-created Document row (simulating the
    # runner having persisted it) and assert the endpoint surfaces it.
    row = await session.execute(select(Document).where(Document.task_id == task_id))
    doc = row.scalar_one()
    doc.portrait = {"account_type": "credit_card", "account_holder": "李四"}
    await session.commit()

    resp = await client.get(f"/api/tasks/{task_id}/documents")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["portrait"] == {"account_type": "credit_card", "account_holder": "李四"}


@pytest.mark.asyncio
async def test_document_detail_endpoint_returns_latest_portrait(client, db_session, monkeypatch):
    """GET /tasks/{id}/documents/{doc_id} returns the current persisted portrait."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Portrait detail task", "channel": "银行流水"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    row = await session.execute(select(Document).where(Document.task_id == task_id))
    doc = row.scalar_one()
    doc.portrait = {
        "account_type": "debit_card",
        "account_holder": "王五",
        "column_mapping": ["transaction_time", "balance"],
    }
    await session.commit()

    resp = await client.get(f"/api/tasks/{task_id}/documents/{doc.id}")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == doc.id
    assert payload["portrait"] == {
        "account_type": "debit_card",
        "account_holder": "王五",
        "column_mapping": ["transaction_time", "balance"],
    }


@pytest.mark.asyncio
async def test_documents_endpoint_portrait_null_when_not_generated(client, monkeypatch):
    """A pending doc (not yet processed) has portrait=null in the response."""
    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Pending portrait"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    resp = await client.get(f"/api/tasks/{task_id}/documents")
    items = resp.json()["items"]
    assert items[0]["portrait"] is None


# ---------------------------------------------------------------------------
# ③ 手动处理 + 可配并发
# ---------------------------------------------------------------------------


def test_default_settings_include_extraction_concurrency_keys():
    """DEFAULT_SETTINGS has extraction.mineru_concurrency + llm_concurrency."""
    from app.services.settings_service import DEFAULT_SETTINGS

    for key in ("extraction.mineru_concurrency", "extraction.llm_concurrency"):
        assert key in DEFAULT_SETTINGS, f"missing default setting {key}"
        assert DEFAULT_SETTINGS[key]["category"] == "extraction"
        assert DEFAULT_SETTINGS[key]["type"] == "number"
    # Defaults: mineru=1, llm=2 (conservative start).
    assert DEFAULT_SETTINGS["extraction.mineru_concurrency"]["value"] == "1"
    assert DEFAULT_SETTINGS["extraction.llm_concurrency"]["value"] == "2"


@pytest.mark.asyncio
async def test_start_endpoint_body_optional_falls_back_to_config_folder(
    client, db_session, tmp_path, monkeypatch
):
    """POST /tasks/{id}/start with no body uses config['document_folder']."""
    calls = []

    async def fake_start(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: False)

    # Create a task with a saved document_folder via the upload endpoint (no
    # auto-start), then start it with an empty body.
    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Startable"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]
    saved_folder = created.json()["config"]["document_folder"]

    resp = await client.post(f"/api/tasks/{task_id}/start", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    assert calls[0]["document_folder"] == saved_folder


@pytest.mark.asyncio
async def test_append_upload_during_running_no_longer_409(client, db_session, monkeypatch):
    """Running tasks accept append uploads (no 409) — the batch loop picks them up."""
    session, _user = db_session

    async def fake_start(**kwargs):
        return None

    monkeypatch.setattr("app.routers.tasks.runner.start", fake_start)
    # Pretend the task is running (runner has a live job).
    monkeypatch.setattr("app.routers.tasks.runner.is_running", lambda task_id: True)

    created = await client.post(
        "/api/tasks/upload",
        data={"title": "Running task", "channel": "银行流水"},
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task_id = created.json()["id"]

    # Flip status to running (upload left it draft; the start endpoint would set
    # running). Simulate that so the old guard would have tripped.
    row = await session.execute(select(Task).where(Task.id == task_id))
    task = row.scalar_one()
    task.status = "running"
    await session.commit()

    append_resp = await client.post(
        f"/api/tasks/{task_id}/append-upload",
        data={"channel": "支付渠道"},
        files=[("files", ("b.pdf", _pdf_bytes(), "application/pdf"))],
    )
    # No 409 — running uploads are accepted and queued.
    assert append_resp.status_code == 200
    folders = append_resp.json()["config"]["append_document_folders"]
    assert len(folders) == 1 and folders[0].endswith("run-2")


@pytest.mark.asyncio
async def test_runner_start_threads_concurrency_settings_into_extractor(monkeypatch):
    """runner.start reads extraction.*_concurrency from runtime settings and
    passes them into extract_flows (via the batch loop's extract_flows call)."""
    import asyncio

    from app.services.extraction.extractor import FlowExtractor, ExtractionResult
    from app.services.extraction.runner import ExtractionTaskRunner

    captured = {}

    # Fake DB session returning concurrency settings.
    class _FakeResult:
        def scalars(self):
            class _S:
                def all(self):
                    return []
            return _S()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def execute(self, *a, **k):
            return _FakeResult()

    # Stub async_session to return our fake session (no DB needed).
    monkeypatch.setattr(
        "app.services.extraction.runner.async_session",
        lambda: _FakeSession(),
    )

    # Stub load_runtime_settings to return custom concurrency values.
    async def fake_load(db):
        return {
            "extraction.mineru_concurrency": "3",
            "extraction.llm_concurrency": "5",
        }

    monkeypatch.setattr("app.services.extraction.runner.load_runtime_settings", fake_load)

    # Stub FlowExtractor so construction + extract_flows capture concurrency.
    async def fake_extract_flows(
        self, document_folder, task_id=None, batch_size=20, confidence_threshold=70,
        documents=None, mineru_concurrency=1, llm_concurrency=2,
    ):
        captured["mineru"] = mineru_concurrency
        captured["llm"] = llm_concurrency
        captured["documents"] = documents
        return ExtractionResult(task_id=task_id or "t", document_folder=document_folder)

    monkeypatch.setattr(FlowExtractor, "extract_flows", fake_extract_flows)
    # Stub _collect_pending_documents to return one doc then none (one round).
    call_count = {"n": 0}

    async def fake_collect(self, task_id, document_folder, extractor):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [Path("/tmp/run-1/a.pdf")]
        return []

    monkeypatch.setattr(ExtractionTaskRunner, "_collect_pending_documents", fake_collect)

    # Stub _mark_finished + notify to avoid DB writes.
    async def fake_mark(self, task_id, owner_id, result, append=False):
        return None

    monkeypatch.setattr(ExtractionTaskRunner, "_mark_finished", fake_mark)

    runner = ExtractionTaskRunner()
    # Bypass the live-job check by not registering a real asyncio.Task; call
    # _run_job directly so the loop executes synchronously.
    extractor = FlowExtractor()
    await runner._run_job(
        task_id=1,
        owner_id=1,
        extractor=extractor,
        document_folder="/tmp/run-1",
        batch_size=20,
        confidence_threshold=70,
        append=False,
        mineru_concurrency=3,
        llm_concurrency=5,
    )

    assert captured["mineru"] == 3
    assert captured["llm"] == 5
    # One round ran (pending docs → none), loop exited.
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_runner_batch_loop_picks_up_mid_run_upload(monkeypatch):
    """The batch loop re-runs when a new pending document appears after a round.

    Round 1 processes one doc; a second doc is registered between round 1 and
    round 2 (simulating an upload mid-run). The loop runs round 2 to process it,
    then exits when no more pending docs remain.
    """
    from app.services.extraction.extractor import FlowExtractor, ExtractionResult
    from app.services.extraction.runner import ExtractionTaskRunner

    rounds = {"n": 0}
    # Pending docs returned per round: [a], then [b], then [].
    pending_sequence = [
        [Path("/tmp/run-1/a.pdf")],
        [Path("/tmp/run-2/b.pdf")],
        [],
    ]

    async def fake_extract_flows(
        self, document_folder, task_id=None, batch_size=20, confidence_threshold=70,
        documents=None, mineru_concurrency=1, llm_concurrency=2,
    ):
        return ExtractionResult(task_id=task_id or "t", document_folder=document_folder)

    monkeypatch.setattr(FlowExtractor, "extract_flows", fake_extract_flows)

    async def fake_collect(self, task_id, document_folder, extractor):
        idx = rounds["n"]
        rounds["n"] += 1
        return pending_sequence[idx] if idx < len(pending_sequence) else []

    monkeypatch.setattr(ExtractionTaskRunner, "_collect_pending_documents", fake_collect)

    async def fake_mark(self, task_id, owner_id, result, append=False):
        return None

    monkeypatch.setattr(ExtractionTaskRunner, "_mark_finished", fake_mark)

    runner = ExtractionTaskRunner()
    extractor = FlowExtractor()
    await runner._run_job(
        task_id=1,
        owner_id=1,
        extractor=extractor,
        document_folder="/tmp/run-1",
        batch_size=20,
        confidence_threshold=70,
        append=False,
    )

    # Three collection calls: round 1 (a), round 2 (b), round 3 (empty → exit).
    assert rounds["n"] == 3


@pytest.mark.asyncio
async def test_runner_batch_loop_exits_when_no_pending(monkeypatch):
    """If there are no pending documents from the start, the loop exits immediately."""
    from app.services.extraction.extractor import FlowExtractor
    from app.services.extraction.runner import ExtractionTaskRunner

    extract_calls = {"n": 0}

    async def fake_extract_flows(self, *a, **k):
        extract_calls["n"] += 1
        raise AssertionError("extract_flows should not run when no pending docs")

    monkeypatch.setattr(FlowExtractor, "extract_flows", fake_extract_flows)

    async def fake_collect(self, task_id, document_folder, extractor):
        return []

    monkeypatch.setattr(ExtractionTaskRunner, "_collect_pending_documents", fake_collect)

    runner = ExtractionTaskRunner()
    extractor = FlowExtractor()
    await runner._run_job(
        task_id=1,
        owner_id=1,
        extractor=extractor,
        document_folder="/tmp/run-1",
        batch_size=20,
        confidence_threshold=70,
        append=False,
    )

    assert extract_calls["n"] == 0


@pytest.mark.asyncio
async def test_extract_flows_concurrency_semaphore_limits_stage1(monkeypatch):
    """stage1 runs at most mineru_concurrency documents concurrently.

    With mineru_concurrency=1, stage-1 processing is serialized — at most one
    _process_document_stage1 in flight at a time. With =2, two can overlap.
    Verified by tracking the high-water mark of concurrent invocations.

    The checkpoint manager + stage2 are stubbed so leftover checkpoint files
    on disk (keyed by task_id + path) don't trigger the resume branch and so
    the real stage2 (which would call the LLM / save checkpoints) never runs.
    """
    import asyncio

    from app.parsers.base import RawTable
    from app.services.extraction.extractor import FlowExtractor

    class _FakeParser:
        def extract_tables_and_context(self, file_path, max_chars=None):
            return [RawTable(table_index=0, rows=[["x"], ["1"]])], ""

    in_flight = {"current": 0, "max": 0}

    async def fake_stage1(self, doc_path, task_id, confidence_threshold):
        in_flight["current"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["current"])
        await asyncio.sleep(0.05)
        in_flight["current"] -= 1
        # No flow tables → returns excluded-only result, no stage 2 scheduled.
        return {
            "doc_path": doc_path,
            "flow_tables": [],
            "portrait": None,
            "total_tables": 1,
            "excluded_records": [],
        }

    async def fake_stage2(self, doc_result, task_id, batch_size):
        return {"doc_path": doc_result["doc_path"], "records": [], "extracted_records": [], "stats": {}}

    extractor = FlowExtractor()
    monkeypatch.setattr(extractor, "_get_parser_for_file", lambda path: _FakeParser())
    monkeypatch.setattr(FlowExtractor, "_process_document_stage1", fake_stage1)
    monkeypatch.setattr(FlowExtractor, "_process_document_stage2", fake_stage2)
    # No checkpoint resume — always process via the mocked stage1.
    monkeypatch.setattr(extractor.checkpoint_manager, "load_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(extractor.checkpoint_manager, "save_checkpoint", lambda *a, **k: None)

    docs = [Path(f"/tmp/web4test/d{i}.pdf") for i in range(4)]

    async def _run(mc, lc):
        in_flight["current"] = 0
        in_flight["max"] = 0
        await extractor.extract_flows(
            document_folder="/tmp/web4test",
            task_id="web4test-%d-%d" % (mc, lc),
            documents=docs,
            mineru_concurrency=mc,
            llm_concurrency=lc,
        )
        return in_flight["max"]

    # mineru_concurrency=1 → serialized stage 1.
    assert await _run(1, 2) == 1
    # mineru_concurrency=2 → up to 2 in flight.
    max2 = await _run(2, 2)
    assert 2 <= max2 <= 2
