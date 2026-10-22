from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings

# Create async database engine
engine: AsyncEngine = create_async_engine(
    str(get_settings().database_url), pool_size=5, pool_pre_ping=True, max_overflow=10
)

# Create a session factory object that creates database sessions
session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine, expire_on_commit=False
)


# Define dependency for database
async def get_db() -> AsyncGenerator[AsyncSession | None]:
    async with session_factory() as db:
        yield db
