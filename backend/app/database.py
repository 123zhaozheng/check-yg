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
        Collaborator,
        CustomerList,
        CustomerListItem,
        Document,
        ExportFile,
        Finding,
        FlowRecordRow,
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


async def _run_alembic_upgrade() -> None:
    """Run Alembic migrations to head against the configured (non-sqlite) DB.

    Alembic 的迁移走同步路径（env.py 用 psycopg 同步驱动），所以在独立
    线程里执行同步 ``command.upgrade``，避免阻塞 async 事件循环，也避免在
    运行中的事件循环里嵌套 ``asyncio.run``。
    """
    import asyncio
    import pathlib

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(pathlib.Path(__file__).resolve().parent.parent / "alembic.ini"))
    # env.py 会从 settings 读连接串并切到 psycopg 同步驱动，这里不覆盖。
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(cfg, "head"))


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
    }
    for column, column_type in docs_additions.items():
        if column not in docs_existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE documents ADD COLUMN {column} {column_type}"
            )

    # reports: status (S7 软态 draft|final). Additive only — new tables
    # (report_chapters / report_annotations) are created by create_all above.
    reports_result = await conn.exec_driver_sql("PRAGMA table_info(reports)")
    reports_existing = {row[1] for row in reports_result.fetchall()}
    if "status" not in reports_existing:
        await conn.exec_driver_sql(
            "ALTER TABLE reports ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'draft'"
        )
