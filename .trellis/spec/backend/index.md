# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines for backend development in the
员工-客户金额往来审计系统 (Employee-Customer Money Transaction Audit System) —
a PyQt5 desktop application with AI-powered document parsing and matching.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | ✅ Done |
| [Database Guidelines](./database-guidelines.md) | JSON/Excel persistence, checkpoint patterns | ✅ Done |
| [Error Handling](./error-handling.md) | Error types, handling strategies, UI error display | ✅ Done |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns, testing | ✅ Done |
| [Logging Guidelines](./logging-guidelines.md) | Structured logging, log levels, Chinese messages | ✅ Done |

---

## Quick Reference

- **Framework**: PyQt5 desktop app (not a web service)
- **Entry point**: `main.py`
- **Config**: `~/.check-yg/config.yaml` via `get_config()` singleton
- **Storage**: JSON checkpoints + Excel files (no database)
- **Logging**: Standard `logging` module, `logging.getLogger(__name__)`
- **Testing**: `unittest` with module-level stubs for heavy deps
- **Language**: English identifiers, Chinese strings/comments

---

**Language**: All documentation is written in **English** with Chinese terms where they match the domain.
