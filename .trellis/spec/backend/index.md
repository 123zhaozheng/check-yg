# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines for backend development in the
员工-客户金额往来审计系统 (智行卫士 / Employee-Customer Money Transaction Audit
System) — a FastAPI backend with AI-powered document parsing, cleaning,
analysis, and reporting, consumed by a SPA frontend (`frontend/`).

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | ✅ Done |
| [Database Guidelines](./database-guidelines.md) | PostgreSQL + Alembic + JSONB, checkpoint patterns | ✅ Done |
| [Error Handling](./error-handling.md) | Error types, handling strategies, UI error display | ✅ Done |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns, testing | ✅ Done |
| [Logging Guidelines](./logging-guidelines.md) | Structured logging, log levels, Chinese messages | ✅ Done |

---

## Quick Reference

- **Framework**: FastAPI (async) + SQLAlchemy 2.x async + pydantic-ai
- **Entry point**: `backend/app/main.py`（`uvicorn app.main:app` from `backend/`）
- **Config**: `backend/app/config.py` pydantic-settings（env / `.env`）
- **Storage**: PostgreSQL（asyncpg 运行时 / psycopg 供 Alembic）+ JSON checkpoint（抽取断点续传）+ Excel
- **Migrations**: Alembic（`backend/migrations/`，生产走 `alembic upgrade head`）
- **Auth**: JWT access+refresh in httpOnly cookies（SameSite=Strict）
- **LLM**: pydantic-ai v1.107.0（OpenAIChatModel+OpenAIProvider，模块级单例）
- **Logging**: Standard `logging` module, `logging.getLogger(__name__)`
- **Testing**: `pytest` + `pytest-asyncio`（sqlite 内存库 + mock LLM agent）
- **Language**: English identifiers, Chinese strings/comments

---

**Language**: All documentation is written in **English** with Chinese terms where they match the domain.
