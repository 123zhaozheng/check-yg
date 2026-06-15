"""Database configuration and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)

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
    """Initialize database tables and seed default data."""
    from app.models import (  # noqa: F401
        Collaborator,
        CustomerList,
        CustomerListItem,
        Document,
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
    from app.auth.password import hash_password

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
