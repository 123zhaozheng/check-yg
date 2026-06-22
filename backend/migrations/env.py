"""Alembic environment.

读取 schema 元数据从 ``app.models.base.Base``，连接串从 ``app.config.settings``
（与运行时同一份配置）。使用同步驱动（psycopg）跑迁移——运行时应用用 asyncpg，
但 Alembic 迁移走同步路径最稳妥，避免在已有事件循环里嵌套 ``asyncio.run``。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings

# 导入所有模型，确保 metadata 完整
from app.models import (  # noqa: F401
    Collaborator,
    CustomerList,
    CustomerListItem,
    Document,
    ExportFile,
    Finding,
    FlowRecordRow,
    Report,
    Review,
    ReviewMatch,
    Role,
    Setting,
    Task,
    TaskLog,
    User,
)
from app.models.base import Base

config = context.config

# 运行时用 asyncpg（postgresql+asyncpg://），Alembic 同步迁移用 psycopg。
_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
config.set_main_option("sqlalchemy.url", _url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to a file)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a synchronous engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
