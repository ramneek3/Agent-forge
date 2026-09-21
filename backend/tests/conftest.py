"""Shared pytest fixtures."""

import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Configure test environment before app imports
os.environ["APP_ENV"] = "test"
os.environ["USE_SQLITE"] = "true"
os.environ["SQLITE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["LLM_MOCK_MODE"] = "true"
os.environ["AUTH_ENABLED"] = "false"
os.environ["USE_LOCAL_EMBEDDINGS"] = "false"
os.environ["DEBUG"] = "false"

from app.core.config import get_settings

get_settings.cache_clear()

from app.db.session import Base, get_db
from app.llm.registry import reset_provider_registry
from app.main import create_app


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    Session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    reset_provider_registry()
    get_settings.cache_clear()
    app = create_app()
    Session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Skip lifespan DB init against real settings — tables already created
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
