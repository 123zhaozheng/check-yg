# Logging Guidelines

> How logging is done in this project.

---

## Overview

The project uses **standard Python `logging`** module, configured in `main.py`.
No third-party logging libraries.

---

## Setup

Logging is initialized in `main.py::setup_logging()`:

```python
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(),           # Console (for development)
        logging.FileHandler(log_file, encoding='utf-8'),
    ]
)
```

- Log directory: `~/.check-yg/logs/`
- Log file: `audit_YYYYMMDD.log` (one file per day)
- **Always `encoding='utf-8'`** for file handlers (Chinese content)

---

## Log Levels

| Level | When to use | Example |
|---|---|---|
| `DEBUG` | Verbose diagnostic info (not used in production) | `logger.debug("Raw table rows: %d", len(rows))` |
| `INFO` | Normal operational milestones | `logger.info("加载流水: %d 条", len(records))` |
| `WARNING` | Non-critical failures; process continues | `logger.warning("发现 %d 条金额无效的流水，已跳过", count)` |
| `ERROR` | Critical failures; function cannot complete | `logger.error("加载流水Excel失败: %s", e)` |

**Rule of thumb**:
- If the function **returns an error** or **raises**: use `logger.error()`
- If the function **skips bad data and continues**: use `logger.warning()`
- If the function **completes a milestone**: use `logger.info()`

---

## Logger Initialization

Two patterns used in the codebase:

### Module-level logger (most common)

```python
import logging
logger = logging.getLogger(__name__)
```

Used in nearly every module: `config.py`, `reviewer.py`, `checkpoint_manager.py`, etc.

### Per-class logger (in class hierarchies)

```python
# From src/parsers/base.py
class BaseParser(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
```

Used by `BaseParser` subclasses so log messages show the specific parser class name (e.g., `ExcelParser`, `DocxParser`).

**Convention**: use `__name__` for module-level, `self.__class__.__name__` for class-level.

---

## Structured Logging

### Format

```
2024-06-01 14:30:22,123 - src.core.reviewer - INFO - 加载流水: 150 条
2024-06-01 14:30:22,456 - src.core.checkpoint_manager - WARNING - Failed to read checkpoint /path/doc_abc.json: [Errno 2] No such file
```

Fields: `timestamp - logger_name - level - message`

### Message style

- **Chinese messages** for business-domain events: `"加载流水: %d 条"`, `"写回流水Excel失败: %s"`
- **English messages** for infrastructure/IO events: `"Failed to read checkpoint %s: %s"`, `"Configuration loaded from %s"`
- Use `%s`/`%d` formatting (not f-strings) in logger calls for lazy evaluation

```python
# Correct
logger.info("加载客户: %d 个", count)
# Avoid (eagerly formats even if log level is disabled)
logger.info(f"加载客户: {count} 个")
```

---

## What to Log

| Event | Level | What to include |
|---|---|---|
| Task started/completed | INFO | Task ID, document count |
| Data loaded | INFO | Record count, file path |
| Checkpoint saved | INFO (optional) | Task ID, document name |
| API call result | INFO/ERROR | Status code, response snippet |
| Bad data skipped | WARNING | Count, reason |
| File operation failed | WARNING/ERROR | Path, exception message |
| Unexpected state | WARNING | What was expected vs found |

---

## What NOT to Log

- **API keys** — never log `config.llm_api_key` or `config.mineru_public_api_key`
- **Full document content** — log row counts, not raw table HTML
- **Full LLM responses** — log length and status, not the complete response body
- **PII/customer data** — don't log customer names or account numbers in bulk

---

## Common Mistakes

1. **Using f-strings in logger calls** — use `%s`/`%d` for lazy formatting
2. **Logging at ERROR when the process continues normally** — use WARNING instead
3. **Forgetting `encoding='utf-8'`** on FileHandler — Chinese log messages will crash
4. **Creating loggers with hardcoded names** — use `__name__` or `self.__class__.__name__`
5. **Not logging at all on caught exceptions** — always log before `continue` or `return None`
