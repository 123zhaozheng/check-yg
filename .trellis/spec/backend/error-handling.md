# Error Handling

> How errors are handled in this project.

---

## Overview

The project uses a **return-error pattern** for core logic and **QMessageBox** for user-facing errors.
Exceptions are caught at module boundaries; internal core functions generally do not raise into the UI.

Two main patterns:
1. **Return `(result, error_string)` tuples** — parser and utility functions return `(None, "error message")` on failure
2. **Log + continue** — non-critical errors are logged as warnings and the process continues
3. **Log + raise** — critical structural errors (missing files, bad headers) are logged and re-raised

---

## Error Types

No custom exception hierarchy is defined. The project uses:
- Built-in exceptions: `FileNotFoundError`, `ValueError`, `TypeError`
- Third-party exceptions: `pikepdf.PasswordError`
- String error messages returned alongside results

**Dataclasses carry errors**: `ReviewResult.writeback_error: str` stores non-fatal errors that don't block the review.

---

## Error Handling Patterns

### Pattern 1: Return tuple `(result, error)`

Used by parsers and utility functions. Caller checks the error string.

```python
# From src/parsers/pdf_parser.py
try:
    pdf = pikepdf.open(file_path, password=password)
    temp_path = temp_dir / f"decrypted_{uuid.uuid4().hex[:8]}.pdf"
    pdf.save(str(temp_path))
    pdf.close()
    return temp_path, None          # Success: (result, None)
except pikepdf.PasswordError as e:
    logger.error("Password error: %s", e)
    return None, f"密码错误: {e}"    # Failure: (None, error_msg)
except Exception as e:
    logger.error("Decrypt error: %s", e)
    return None, str(e)
```

### Pattern 2: Log warning + continue

Used for non-critical failures where the process should keep going.

```python
# From src/core/reviewer.py
try:
    self._write_back_results(flow_excel_path, best_match_by_row, matches)
except Exception as exc:
    result.writeback_error = str(exc)
    logger.warning("写回流水Excel失败: %s", exc)  # Log but don't raise
```

### Pattern 3: Log error + raise

Used for critical failures in data-loading functions.

```python
# From src/core/reviewer.py
try:
    # ... load flows ...
except Exception as e:
    logger.error("加载流水Excel失败: %s", e)
    raise
```

### Pattern 4: Guard clause with early return

Used for input validation before processing.

```python
# From src/core/reviewer.py
path = Path(excel_path)
if not path.exists():
    raise FileNotFoundError(f"File not found: {excel_path}")
```

---

## API Error Responses

### LLM API errors

```python
# From src/llm/audit_agent.py (pattern)
response = requests.post(url, json=payload, timeout=self.config.llm_timeout)
if response.status_code != 200:
    logger.error("LLM API error: %d %s", response.status_code, response.text[:200])
    return None
```

Pattern: **check status code, log error, return None**. The caller handles the None return.

### MinerU API errors

Similar pattern in `src/parsers/pdf_parser.py` — check response status, log, return `(None, error_msg)`.

---

## UI Error Display

Core-layer errors propagate to UI via return values. The UI layer shows errors via:

```python
# Typical UI pattern (from page files)
QMessageBox.critical(self, "错误", f"加载失败: {error_msg}")
```

- Use `QMessageBox.critical()` for errors, `QMessageBox.warning()` for warnings
- Show Chinese error messages to the user
- Log the English/technical detail to the logger

---

## Common Mistakes

1. **Swallowing exceptions silently** — always log at minimum `logger.warning()` before continuing
2. **Raising exceptions from core into UI** — core should return error strings/tuples; UI decides how to display
3. **Forgetting `finally: wb.close()`** on Excel workbooks — locks the file
4. **Not validating file existence before `openpyxl.load_workbook()`** — raises unhandled `FileNotFoundError`
5. **Using bare `except:`** — always catch specific exceptions or `Exception`, never bare `except:`
