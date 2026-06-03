# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

This project follows pragmatic Python conventions. No linter configuration is enforced
via tooling, but the codebase consistently follows the patterns below.

---

## Environment & Python Version

- **Environment manager**: `uv` (not pip/poetry/conda)
- **Python version**: strictly **3.8** — no higher
- **Forbidden Python 3.9+ features**:
  - Walrus operator (`:=`)
  - `str.removeprefix()` / `str.removesuffix()`
  - Dict merge operator (`|`)
  - `list[0]` type hint syntax (use `List[0]` from `typing`)
  - `@functools.cached_property` (use `@property` with manual cache)

---

## Forbidden Patterns

1. **`src/core/` importing from `src/ui/`** — core must be UI-independent
2. **Bare `except:` clauses** — always catch `Exception` or a specific type
3. **Hardcoded API URLs or keys** — always use `get_config()` for external service configuration
4. **f-strings in logger calls** — use `%s`/`%d` lazy formatting
5. **Chinese variable/function names** — code identifiers are English; Chinese only in strings and comments
6. **Importing `openpyxl` in core without try/finally** — always ensure `wb.close()`
7. **Direct `print()` for output** — use `logging` or UI signals
8. **Python 3.9+ syntax** — project is pinned to Python 3.8

---

## Required Patterns

### 1. UTF-8 encoding on all file I/O

```python
# Always specify encoding for text files
with open(path, "r", encoding="utf-8") as f:
    ...
with open(path, "w", encoding="utf-8") as f:
    ...
```

### 2. Config via singleton

```python
from src.config import get_config

config = get_config()
url = config.llm_url
```

Never hardcode paths or URLs. Access config properties, not raw dict keys.

### 3. Dataclasses for structured data

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class ReviewMatch:
    customer_name: str
    counterparty_name: str
    match_type: str  # "精确匹配" / "脱敏匹配"
    confidence: int

    def to_dict(self) -> dict:
        ...
```

Always provide `to_dict()` for serialization. Use `field(default_factory=list)` for mutable defaults.

### 4. Pathlib over os.path

```python
from pathlib import Path

path = Path(excel_path)
if not path.exists():
    raise FileNotFoundError(...)
```

### 5. Module-level logger

```python
import logging
logger = logging.getLogger(__name__)
```

### 6. File encoding comment

```python
# -*- coding: utf-8 -*-
```

Present on every `.py` file in the codebase.

### 7. Docstrings in Chinese for business logic

```python
def load_flows(self, excel_path: str) -> List[dict]:
    """
    加载流水Excel

    Args:
        excel_path: Excel文件路径

    Returns:
        List[dict]: 流水记录列表
    """
```

---

## Testing Requirements

### Framework

- **unittest** (standard library) — no pytest
- Run: `python -m unittest tests/`

### Test file naming

`test_<module_name>.py` under `tests/`

### Mock strategy

Stub heavy external dependencies at the module level before importing:

```python
# From tests/test_flow_extractor_v2_and_reviewer.py
sys.modules.setdefault("pikepdf", types.ModuleType("pikepdf"))
if "bs4" not in sys.modules:
    bs4_stub = types.ModuleType("bs4")
    class _DummySoup:
        def __init__(self, *args, **kwargs): pass
        def find_all(self, *args, **kwargs): return []
    bs4_stub.BeautifulSoup = _DummySoup
    sys.modules["bs4"] = bs4_stub
```

This pattern replaces `pikepdf`, `bs4`, `docx` with lightweight stubs so tests
run without those packages installed.

### Test helper classes

- `_DummyConfig` — provides config properties without reading YAML files
- `_SpyCheckpointManager` — extends real class to verify method calls
- Use `tempfile.mkdtemp()` for isolated test directories

### What to test

- Core logic: matching, amount parsing, checkpoint save/load
- Edge cases: empty inputs, missing files, invalid data
- Integration: extractor → reviewer pipeline (with mocked LLM)

### What NOT to test

- UI rendering (PyQt5 widgets)
- External API calls (mock them)
- Config file reading (use `_DummyConfig`)

---

## Code Review Checklist

- [ ] No `src/core/` → `src/ui/` imports
- [ ] All file I/O uses `encoding='utf-8'`
- [ ] Excel workbooks closed in `try/finally`
- [ ] Logger uses `%s` not f-strings
- [ ] No hardcoded API URLs/keys
- [ ] Dataclasses have `to_dict()` for serialization
- [ ] Mutable defaults use `field(default_factory=...)`
- [ ] Error paths logged before returning/raising
- [ ] `# -*- coding: utf-8 -*-` at file top
- [ ] Chinese in strings/comments only, English in identifiers
