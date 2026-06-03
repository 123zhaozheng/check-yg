# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

This project does **not use a traditional database** (no SQLite, PostgreSQL, or MySQL).
Data persistence relies on:

1. **YAML config** — `~/.check-yg/config.yaml` (application settings)
2. **JSON checkpoint files** — `~/.check-yg/checkpoints/{task_id}/doc_*.json` and `task.json`
3. **JSON review history** — `~/.check-yg/reviews/{review_id}.json`
4. **Excel files** — source data and output reports via `openpyxl`

All file I/O uses `pathlib.Path`, `json`, and `yaml` — no ORM.

---

## Query Patterns

### JSON file reads

```python
# From src/core/checkpoint_manager.py
@staticmethod
def _read_json(path: Path) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to read checkpoint %s: %s", path, exc)
        return None
```

Pattern: **try/except with warning log, return None on failure**. Never crash on a bad checkpoint file.

### JSON file writes

```python
@staticmethod
def _write_json(path: Path, data: Dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Failed to write checkpoint %s: %s", path, exc)
```

Pattern: **`ensure_ascii=False` for Chinese text, `indent=2` for readability**, warning on failure.

### Excel reads

```python
# From src/core/reviewer.py
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
ws = wb.active
rows_iter = ws.iter_rows(values_only=True)
# ... process rows ...
wb.close()
```

Pattern: **`read_only=True, data_only=True`** for reading; always close the workbook.

### Excel writes

```python
# From src/core/reviewer.py
wb = openpyxl.load_workbook(path)
try:
    ws = wb.active
    # ... write cells ...
    wb.save(path)
finally:
    wb.close()
```

Pattern: **`try/finally` with `wb.close()`** for writes; save then close.

---

## Data Storage Structure

### Config (`~/.check-yg/config.yaml`)

```yaml
mineru:
  mode: local
  url: http://localhost:8000
llm:
  url: https://api.openai.com/v1
  model: gpt-4
flow_extraction:
  batch_size: 20
  checkpoint_interval: 50
```

### Checkpoints (`~/.check-yg/checkpoints/{task_id}/`)

```
{task_id}/
├── task.json           # Task metadata: id, title, status, documents list
└── doc_{hash}.json     # Per-document state: stage, extracted data, progress
```

- Document hash: `md5(name|path)[:16]` — see `CheckpointManager._doc_hash()`
- Task statuses: `pending`, `extracting`, `normalizing`, `completed`, `canceled`, `failed`
- Document statuses: `pending`, `stage1_done`, `stage2_running`, `normalizing`, `completed`, `failed`, `canceled`
- `document_folder`: **`List[str]`** — list of all folder paths added to the task (was `str`, auto-converted on load via `_normalize_document_folder`)

### Review History (`~/.check-yg/reviews/{review_id}.json`)

Serialized `ReviewResult` dataclass as JSON dict.

---

## Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Config file | `config.yaml` in `~/.check-yg/` | |
| Checkpoint dir | `{task_id}/` under `checkpoints/` | `task_20240601/` |
| Doc checkpoint | `doc_{md5_hash}.json` | `doc_a1b2c3d4e5f6g7h8.json` |
| Task meta | `task.json` | |
| Review file | `{timestamp}.json` | `20240601_143022.json` |
| Excel output | `extract_{task_id}.json` in `data/reports/` | |

---

## Common Mistakes

1. **Forgetting `wb.close()` on Excel workbooks** — always use `try/finally` or context-style cleanup
2. **Not using `encoding='utf-8'`** for JSON/YAML reads/writes — Chinese text will corrupt without it
3. **Writing to checkpoints without `ensure_ascii=False`** — causes escaped Unicode in JSON files
4. **Not handling missing checkpoint files gracefully** — `load_document_state()` must return `None`, not crash
5. **Using `openpyxl.load_workbook()` without `read_only=True`** for read-only operations — wastes memory on large files
6. **Treating `document_folder` as `str`** — it was changed to `List[str]` for append-folder support. Always use `_normalize_document_folder()` to handle backward compat (old data stores it as `str`)

---

## Append-Folder Scenario

### 1. Scope / Trigger
- Trigger: User clicks "新增流水目录" on a `completed` task to add more documents
- This requires code-spec depth because it changes the task schema (`document_folder` type) and introduces a cross-layer flow (UI → core → checkpoint)

### 2. Signatures
```python
# checkpoint_manager.py
def append_documents(self, task_id: str, new_folder: str, new_documents: List[str]) -> None
def _normalize_document_folder(self, raw) -> List[str]

# flow_extractor_v2.py
def extract_flows_append(self, task_id: str, new_folder: str, progress: ProgressManager) -> ExtractionResult
def _load_existing_report_records(self, task_id: str) -> List[dict]

# extractor.py (wrapper)
def extract_flows_append(self, task_id: str, new_folder: str, progress: ProgressManager) -> ExtractionResult

# extract_page.py (UI)
def start_append_extraction(self, task_id: str, folder_path: str) -> None
```

### 3. Contracts
- `append_documents(task_id, new_folder, new_documents)`:
  - Appends `new_folder` to `document_folder` list (deduped)
  - Appends `new_documents` to `documents` list (path-deduped against existing)
  - Sets task status to `extracting`
  - Creates checkpoint files for each new document
- `extract_flows_append(task_id, new_folder, progress)`:
  - Returns `ExtractionResult` with `total_documents=0` if no new files found (caller handles UI prompt)
  - Merges old records from existing report JSON + new records into combined report
  - Final status: `completed` (all succeed) or `failed` (any failed)

### 4. Validation & Error Matrix
| Condition | Behavior |
|----------|----------|
| Task status != `completed` | Menu option not shown (UI guard) |
| Selected folder has no supported files | `extract_flows_append` returns `total_documents=0`; UI shows QMessageBox |
| All new files are duplicates of existing | Same as empty folder — treated as 0 new documents |
| Worker already running | `start_append_extraction` shows warning, does not start second worker |
| Extraction error during append | `_is_append` flag reset to False in error handler; task status preserved |
| User cancels during append | Reuses existing cancel mechanism (`_cancel_requested`) |

### 5. Good/Base/Bad Cases
- Good: Select folder with 5 new PDFs → status goes `completed`→`extracting`→`normalizing`→`completed`, all data merged
- Base: Select folder with 3 new + 2 already-processed files → only 3 processed, 2 skipped by path dedup
- Bad: Select empty folder → QMessageBox "该目录下未找到可处理的文档", task status unchanged

### 6. Tests Required
- Unit: `append_documents` dedupes folder paths and document paths
- Unit: `_normalize_document_folder` converts `str`→`[str]`, `None`→`[]`, `list`→`list`
- Unit: `extract_flows_append` returns `total_documents=0` when no new files
- Integration: Full append flow on a completed task (status transitions, data merge)

### 7. Wrong vs Correct
#### Wrong
```python
# Treating document_folder as string
folder = task_data["document_folder"]  # Could be str or list!
scanner.scan_directory(folder)
```
#### Correct
```python
# Always normalize on load
folders = self._normalize_document_folder(task_data.get("document_folder"))
for folder in folders:
    scanner.scan_directory(folder)
```
