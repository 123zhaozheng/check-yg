"""Database configuration and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=not settings.DATABASE_URL.startswith("sqlite"),
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database tables and seed default data.

    生产/本地 pg：走 Alembic ``upgrade head``（schema 由迁移管理，不再用
    ``create_all``）。测试用 SQLite 内存库：保留 ``create_all`` + 轻量迁移，
    不依赖 Alembic。
    """
    from app.models import (  # noqa: F401
        AuditConversation,
        AuditDimension,
        Collaborator,
        CustomerList,
        CustomerListItem,
        Document,
        ExportFile,
        Finding,
        FlowRecordRow,
        KeywordCard,
        KeywordHit,
        KeywordTerm,
        LLMModel,
        LLMModelAssignment,
        Report,
        ReportAnnotation,
        ReportChapter,
        Review,
        ReviewMatch,
        Role,
        Setting,
        Task,
        TaskLog,
        User,
    )
    from app.models.base import Base
    from app.auth.password import hash_password

    if settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _run_lightweight_migrations(conn)
    else:
        await _run_alembic_upgrade()

    # Seed default roles and admin user
    from sqlalchemy import select
    async with async_session() as session:
        # Create default roles if not exist
        for role_name in ["admin", "auditor", "viewer"]:
            result = await session.execute(
                select(Role).where(Role.name == role_name)
            )
            if not result.scalar_one_or_none():
                session.add(Role(name=role_name))
        await session.commit()

        # Create default admin user if not exist
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        if not result.scalar_one_or_none():
            admin_role = (await session.execute(
                select(Role).where(Role.name == "admin")
            )).scalar_one()
            session.add(User(
                username="admin",
                email="admin@check-yg.com",
                hashed_password=hash_password("admin123"),
                role_id=admin_role.id,
                is_active=True,
            ))
            await session.commit()

        # Seed default LLM model cards (06-23-llm-model-card). Idempotent —
        # only inserts cards whose display_name isn't already present.
        # Assignments stay empty (user picks per-stage in the settings UI).
        from app.services.llm_model_service import seed_default_llm_models
        await seed_default_llm_models(session)


async def _run_alembic_upgrade() -> None:
    """Run Alembic migrations to head against the configured (non-sqlite) DB.

    在 asyncio 事件循环里直接跑同步 ``command.upgrade``（含原先的
    ``run_in_executor`` 与直接同步调用两种写法）都会卡死：alembic env.py 的
    ``fileConfig`` 会重配 root logging，与 uvicorn/asyncio 正在使用的 logging
    handler 冲突，导致 ``upgrade`` 永不返回 → lifespan 卡在 ``Waiting for
    application startup`` → 应用不接请求 → 无任何接口/业务日志。

    根因是「在运行中的 asyncio 事件循环所在进程里跑 alembic」，与线程池无关
    （已实测：纯 ``python -c`` 跑 ~0.3s 正常；带 asyncio/uvicorn 跑即卡；
    子进程跑 ~1s 正常）。修法：用同步 ``subprocess.run`` 起独立子进程跑
    ``alembic upgrade head``，把迁移完全隔离到独立进程，不碰当前进程的
    logging 与事件循环。

    不用 ``asyncio.create_subprocess_exec``：Windows 上 uvicorn 用的
    ``SelectorEventLoop`` 不支持子进程（``NotImplementedError``）。同步
    ``subprocess.run`` 阻塞 ~1s，在 lifespan 启动期可接受。

    env.py 从 settings 读连接串并切到 psycopg 同步驱动，子进程继承环境变量即可。
    """
    import pathlib
    import subprocess
    import sys

    backend_dir = pathlib.Path(__file__).resolve().parent.parent
    alembic_ini = backend_dir / "alembic.ini"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head 失败 (exit {result.returncode}): "
            f"{result.stderr or result.stdout}"
        )


async def _run_lightweight_migrations(conn) -> None:
    """Apply additive SQLite migrations for deployments using create_all."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    result = await conn.exec_driver_sql("PRAGMA table_info(review_matches)")
    existing = {row[1] for row in result.fetchall()}
    additions = {
        "counterparty_name": "VARCHAR(255)",
        "counterparty_account": "VARCHAR(255)",
        "source_file": "VARCHAR(255)",
        "transaction_time": "VARCHAR(100)",
        "amount": "VARCHAR(100)",
        "summary": "TEXT",
        "record_payload": "JSON",
    }
    for column, column_type in additions.items():
        if column not in existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE review_matches ADD COLUMN {column} {column_type}"
            )

    # documents: channel + size_bytes (S4 data import). Additive only.
    docs_result = await conn.exec_driver_sql("PRAGMA table_info(documents)")
    docs_existing = {row[1] for row in docs_result.fetchall()}
    docs_additions = {
        "channel": "VARCHAR(50)",
        "size_bytes": "INTEGER",
        "portrait": "JSON",
    }
    for column, column_type in docs_additions.items():
        if column not in docs_existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE documents ADD COLUMN {column} {column_type}"
            )

    # reports: status (S7/S8 软态 draft|generating|generated|failed|final).
    # Additive only — new tables
    # (report_chapters / report_annotations) are created by create_all above.
    reports_result = await conn.exec_driver_sql("PRAGMA table_info(reports)")
    reports_existing = {row[1] for row in reports_result.fetchall()}
    if "status" not in reports_existing:
        await conn.exec_driver_sql(
            "ALTER TABLE reports ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'draft'"
        )

    # exports: scope (S8 导出范围 report/raw/standard/findings). Additive only —
    # nullable so legacy excel/bundle rows stay compatible (不删减精神).
    exports_result = await conn.exec_driver_sql("PRAGMA table_info(exports)")
    exports_existing = {row[1] for row in exports_result.fetchall()}
    if "scope" not in exports_existing:
        await conn.exec_driver_sql(
            "ALTER TABLE exports ADD COLUMN scope VARCHAR(50)"
        )

    # flow_records: balance (06-28-balance-column-check). Additive only — nullable
    # so 无余额列文档 (信用卡等) rows stay compatible.
    fr_result = await conn.exec_driver_sql("PRAGMA table_info(flow_records)")
    fr_existing = {row[1] for row in fr_result.fetchall()}
    if "balance" not in fr_existing:
        await conn.exec_driver_sql(
            "ALTER TABLE flow_records ADD COLUMN balance VARCHAR(100)"
        )
