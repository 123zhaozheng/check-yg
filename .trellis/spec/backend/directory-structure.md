# Directory Structure

> How backend code is organized in this project.

---

## Overview

This is a **PyQt5 desktop application** (员工-客户金额往来审计系统), not a web service.
The "backend" layer is a Python package under `src/` providing core logic, parsers, LLM clients,
and export utilities — all consumed by the UI layer (`src/ui/`).

Entry point: `main.py` at the repo root.

---

## Directory Layout

```
check-yg/
├── main.py                    # Application entry point (PyQt5 bootstrap)
├── requirements.txt           # Dependencies
├── AGENTS.md                  # Agent instructions (Trellis managed)
├── src/                       # Main source package
│   ├── __init__.py
│   ├── config.py              # Config singleton (YAML-backed)
│   ├── core/                  # Business logic (no UI, no I/O side-effects beyond checkpoint files)
│   │   ├── checkpoint_manager.py   # Task checkpoint persistence
│   │   ├── customer.py             # Customer list management
│   │   ├── extraction_result.py    # Extraction result dataclass
│   │   ├── extractor.py            # V1 extractor (legacy wrapper)
│   │   ├── flow_extractor_v2.py    # V2 AI-powered two-stage extractor
│   │   ├── matcher.py              # Name matching (exact/desensitized/fuzzy)
│   │   ├── progress_manager.py     # Progress reporting interface
│   │   ├── review_history.py       # Review result persistence
│   │   ├── reviewer.py             # Simplified review (no LLM, pure matching)
│   │   ├── scanner.py              # Document file scanner
│   │   └── task_manager.py         # High-level task orchestration
│   ├── export_flows/               # Export and skill bundle generation
│   │   ├── skill_export.py             # Single-task skill export
│   │   ├── board_skill_export.py       # Multi-task board skill export
│   │   ├── skill_assets/scripts/       # Export script templates
│   │   └── board_skill_assets/scripts/ # Board export script templates
│   ├── llm/                  # LLM integration layer
│   │   ├── audit_agent.py          # Report generation and QA via LLM
│   │   ├── data_normalizer.py      # AI row normalization
│   │   └── flow_table_classifier.py  # AI table classification
│   ├── parsers/              # Document parsers
│   │   ├── base.py                 # BaseParser ABC + FlowRecord/RawTable dataclasses
│   │   ├── docx_parser.py          # DOCX parser
│   │   ├── excel_parser.py         # Excel parser
│   │   ├── html_parser.py          # HTML table parser
│   │   └── pdf_parser.py           # MinerU-based PDF parser
│   └── ui/                   # PyQt5 UI layer
│       ├── __init__.py
│       ├── main_window.py          # MainWindow + SettingsDialog
│       ├── styles.py               # UI style constants
│       ├── pages/                  # One file per navigation page
│       └── widgets/                # Reusable UI widgets
└── tests/                    # Unit tests
    ├── test_checkpoint_and_task_manager.py
    ├── test_extraction_result.py
    ├── test_flow_extractor_v2_and_reviewer.py
    ├── test_pdf_parser.py
    └── test_review_history.py
```

---

## Module Organization

### Where new features go

| Feature type | Directory | Example |
|---|---|---|
| Core business logic (no UI) | `src/core/` | `reviewer.py`, `matcher.py` |
| Document parsing | `src/parsers/` | `excel_parser.py` |
| LLM/AI integration | `src/llm/` | `audit_agent.py` |
| UI pages | `src/ui/pages/` | `home_page.py` |
| UI widgets (reusable) | `src/ui/widgets/` | Custom PyQt5 widgets |
| Export/bundle logic | `src/export_flows/` | `skill_export.py` |
| Tests | `tests/` | `test_review_history.py` |

### Rules

- **`src/core/` must not import from `src/ui/`**. Core is UI-independent.
- **New parsers** subclass `BaseParser` (see `src/parsers/base.py`) and set `SUPPORTED_EXTENSIONS`.
- **New UI pages** follow the pattern in `src/ui/pages/`: one file per page, each exporting a `*Page(QWidget)` class.
- **LLM modules** access config via `get_config()`, never hardcode API URLs.

---

## Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Python files | `snake_case.py` | `flow_extractor_v2.py` |
| Classes | `PascalCase` | `FlowExtractorV2`, `ReviewMatch` |
| Dataclasses | `PascalCase`, noun phrase | `FlowRecord`, `RawTable`, `ReviewResult` |
| Config keys | `snake_case`, dot-separated for access | `flow_extraction.batch_size` |
| Config properties | `snake_case` with `@property` | `flow_batch_size` |
| Test files | `test_<module_name>.py` | `test_pdf_parser.py` |
| UI page files | `<name>_page.py` | `home_page.py`, `extract_page.py` |
| Chinese strings | Use Chinese directly in string literals | `"密码错误"`, `"精确匹配"` |

---

## Examples

- Well-organized core module: `src/core/reviewer.py` — single responsibility (review logic only), uses dataclasses for results, delegates matching to `NameMatcher`
- Clean parser pattern: `src/parsers/base.py` — ABC with `SUPPORTED_EXTENSIONS` class var and `extract_raw_tables()` abstract method
- Config singleton: `src/config.py` — `get_config()` function returns global instance, dot-notation access, `@property` shortcuts
