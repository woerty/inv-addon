import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def isolate_picnic_credentials(monkeypatch):
    """Keep a developer's real .env credentials out of the test suite.

    Settings reads backend/.env, which on a dev machine may contain real Picnic
    credentials + token path. That would flip the Picnic feature flag on and even
    let tests hit the live API. Force everything empty by default (env vars
    override .env); tests that need credentials set them explicitly afterward
    (pytest runs autouse fixtures before explicitly-requested ones).
    """
    from app.config import get_settings

    monkeypatch.setenv("PICNIC_MAIL", "")
    monkeypatch.setenv("PICNIC_EMAIL", "")
    monkeypatch.setenv("PICNIC_PASSWORD", "")
    monkeypatch.setenv("PICNIC_TOKEN_PATH", "/tmp/nonexistent-test-picnic-token.json")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def mock_lookup_barcode():
    """Mock the barcode lookup to avoid real HTTP calls during tests."""
    with patch(
        "app.routers.inventory.lookup_barcode",
        new=AsyncMock(return_value={"name": "Testprodukt", "category": "Testkategorie"}),
    ):
        yield


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
