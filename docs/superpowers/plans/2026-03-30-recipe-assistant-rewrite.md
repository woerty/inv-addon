# Recipe Assistant Rewrite - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete rewrite of the Recipe Assistant HA Add-on from Flask/JS/SQLite/OpenAI to FastAPI/TypeScript/PostgreSQL/Claude with camera barcode scanning.

**Architecture:** FastAPI backend with async SQLAlchemy + PostgreSQL, React 19 + TypeScript + Vite frontend. Single Docker container with Supervisor managing Postgres + uvicorn. Claude for chat/recipes, DALL-E for images only. Camera-based barcode scanner via react-zxing.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL 16, Anthropic SDK, OpenAI SDK (images only), httpx, React 19, TypeScript, Vite, MUI 6, react-zxing, react-router-dom 7, react-markdown

---

## File Map

### Backend (`recipe-assistant/backend/`)

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Python dependencies and project metadata |
| `alembic.ini` | Alembic config pointing to `app/` |
| `alembic/env.py` | Alembic environment with async engine |
| `alembic/versions/001_initial.py` | Initial migration (all 4 tables) |
| `app/__init__.py` | Empty |
| `app/main.py` | FastAPI app, lifespan, static file mount, SPA fallback |
| `app/config.py` | Pydantic BaseSettings, HA options.json + .env |
| `app/database.py` | Async engine, AsyncSession factory, get_db dependency |
| `app/models/__init__.py` | Re-export all models |
| `app/models/inventory.py` | InventoryItem, StorageLocation |
| `app/models/chat.py` | ChatMessage |
| `app/models/log.py` | InventoryLog |
| `app/schemas/__init__.py` | Empty |
| `app/schemas/inventory.py` | Inventory + StorageLocation request/response schemas |
| `app/schemas/recipe.py` | Recipe schema |
| `app/schemas/chat.py` | Chat request/response schemas |
| `app/routers/__init__.py` | Empty |
| `app/routers/inventory.py` | /api/inventory/* endpoints |
| `app/routers/storage.py` | /api/storage-locations/* endpoints |
| `app/routers/assistant.py` | /api/assistant/* endpoints |
| `app/services/__init__.py` | Empty |
| `app/services/barcode.py` | OpenFoodFacts async lookup |
| `app/services/ai_chat.py` | Claude chat service |
| `app/services/ai_recipes.py` | Claude recipe suggestions |
| `app/services/ai_images.py` | DALL-E image generation |
| `tests/__init__.py` | Empty |
| `tests/conftest.py` | Test DB, async client fixture, test settings |
| `tests/test_inventory.py` | Inventory CRUD tests |
| `tests/test_storage.py` | Storage location tests |
| `tests/test_barcode.py` | Barcode service tests |
| `tests/test_assistant.py` | AI service tests (mocked) |

### Frontend (`recipe-assistant/frontend/`)

| File | Responsibility |
|------|---------------|
| `package.json` | Dependencies and scripts |
| `vite.config.ts` | Vite config with `/api` proxy to backend |
| `tsconfig.json` | TypeScript config |
| `tsconfig.node.json` | TS config for Vite/Node files |
| `index.html` | HTML entry point |
| `src/main.tsx` | React entry, MUI theme |
| `src/App.tsx` | Router with all routes |
| `src/types/index.ts` | Shared TypeScript interfaces |
| `src/api/client.ts` | Central fetch wrapper, all API calls |
| `src/hooks/useInventory.ts` | Inventory state + CRUD operations |
| `src/hooks/useScanner.ts` | Camera barcode detection + cooldown |
| `src/hooks/useChat.ts` | Chat state + send/clear/history |
| `src/components/Navbar.tsx` | Navigation bar |
| `src/components/NotificationProvider.tsx` | Context + Snackbar for app-wide notifications |
| `src/pages/InventoryPage.tsx` | Inventory table with search, sort, inline edit |
| `src/pages/ScanPage.tsx` | Full scan page with camera + manual input |
| `src/pages/ScanStationPage.tsx` | Dedicated iPad scan station |
| `src/pages/RecipesPage.tsx` | Recipe suggestions + DALL-E images |
| `src/pages/ChatPage.tsx` | Chat assistant |

### Container (`recipe-assistant/`)

| File | Responsibility |
|------|---------------|
| `config.json` | HA Add-on manifest |
| `Dockerfile` | Multi-stage build |
| `run.sh` | Init Postgres data dir + launch supervisor |
| `supervisord.conf` | Postgres + Alembic + uvicorn |
| `repository.json` | HA repository metadata (project root) |

---

## Task 1: Backend Project Scaffolding

**Files:**
- Create: `recipe-assistant/backend/pyproject.toml`
- Create: `recipe-assistant/backend/app/__init__.py`
- Create: `recipe-assistant/backend/app/models/__init__.py`
- Create: `recipe-assistant/backend/app/schemas/__init__.py`
- Create: `recipe-assistant/backend/app/routers/__init__.py`
- Create: `recipe-assistant/backend/app/services/__init__.py`
- Create: `recipe-assistant/backend/tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "recipe-assistant-backend"
version = "2.0.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    "httpx>=0.28.0",
    "anthropic>=0.43.0",
    "openai>=1.60.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.25.0",
    "httpx>=0.28.0",
    "aiosqlite>=0.20.0",
]
```

- [ ] **Step 2: Create empty `__init__.py` files**

Create these empty files:
- `recipe-assistant/backend/app/__init__.py`
- `recipe-assistant/backend/app/models/__init__.py`
- `recipe-assistant/backend/app/schemas/__init__.py`
- `recipe-assistant/backend/app/routers/__init__.py`
- `recipe-assistant/backend/app/services/__init__.py`
- `recipe-assistant/backend/tests/__init__.py`

- [ ] **Step 3: Install dependencies**

```bash
cd recipe-assistant/backend
pip install -e ".[dev]"
```

- [ ] **Step 4: Verify installation**

```bash
cd recipe-assistant/backend
python -c "import fastapi; import sqlalchemy; import anthropic; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/
git commit -m "feat: scaffold backend project with pyproject.toml"
```

---

## Task 2: Backend Config Module

**Files:**
- Create: `recipe-assistant/backend/app/config.py`

- [ ] **Step 1: Create `config.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://recipe:recipe@localhost:5432/recipe"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    environment: str = "development"

    @classmethod
    def from_ha_options(cls) -> Settings:
        """Load settings from Home Assistant /data/options.json if it exists."""
        options_path = Path("/data/options.json")
        if options_path.exists():
            options = json.loads(options_path.read_text())
            return cls(
                database_url="postgresql+asyncpg://recipe:recipe@localhost:5432/recipe",
                anthropic_api_key=options.get("anthropic_api_key", ""),
                openai_api_key=options.get("openai_api_key", ""),
                environment="production",
            )
        return cls()


@lru_cache
def get_settings() -> Settings:
    ha_options = Path("/data/options.json")
    if ha_options.exists():
        return Settings.from_ha_options()
    return Settings()
```

- [ ] **Step 2: Verify config loads from .env**

```bash
cd recipe-assistant/backend
echo 'ANTHROPIC_API_KEY=test-key' > .env
python -c "from app.config import get_settings; s = get_settings(); print(s.anthropic_api_key); print(s.environment)"
rm .env
```

Expected:
```
test-key
development
```

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/app/config.py
git commit -m "feat: add config module with HA options.json + .env support"
```

---

## Task 3: Database Setup

**Files:**
- Create: `recipe-assistant/backend/app/database.py`

- [ ] **Step 1: Create `database.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    get_settings().database_url,
    echo=get_settings().environment == "development",
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
```

- [ ] **Step 2: Verify import works**

```bash
cd recipe-assistant/backend
python -c "from app.database import Base, get_db; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/app/database.py
git commit -m "feat: add async SQLAlchemy database setup"
```

---

## Task 4: Database Models

**Files:**
- Create: `recipe-assistant/backend/app/models/inventory.py`
- Create: `recipe-assistant/backend/app/models/chat.py`
- Create: `recipe-assistant/backend/app/models/log.py`
- Modify: `recipe-assistant/backend/app/models/__init__.py`

- [ ] **Step 1: Create `models/inventory.py`**

```python
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StorageLocation(Base):
    __tablename__ = "storage_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    items: Mapped[list[InventoryItem]] = relationship(back_populates="storage_location")


class InventoryItem(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    barcode: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    category: Mapped[str] = mapped_column(String, nullable=False, default="Unbekannt")
    storage_location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("storage_locations.id", ondelete="SET NULL"), nullable=True
    )
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    added_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    storage_location: Mapped[StorageLocation | None] = relationship(
        back_populates="items"
    )
```

- [ ] **Step 2: Create `models/chat.py`**

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
```

- [ ] **Step 3: Create `models/log.py`**

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InventoryLog(Base):
    __tablename__ = "inventory_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Update `models/__init__.py`**

```python
from app.models.inventory import InventoryItem, StorageLocation
from app.models.chat import ChatMessage
from app.models.log import InventoryLog

__all__ = ["InventoryItem", "StorageLocation", "ChatMessage", "InventoryLog"]
```

- [ ] **Step 5: Verify models import cleanly**

```bash
cd recipe-assistant/backend
python -c "from app.models import InventoryItem, StorageLocation, ChatMessage, InventoryLog; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/models/
git commit -m "feat: add SQLAlchemy models for inventory, chat, and log"
```

---

## Task 5: Alembic Setup + Initial Migration

**Files:**
- Create: `recipe-assistant/backend/alembic.ini`
- Create: `recipe-assistant/backend/alembic/env.py`
- Create: `recipe-assistant/backend/alembic/script.py.mako`
- Create: `recipe-assistant/backend/alembic/versions/` (directory)

- [ ] **Step 1: Initialize Alembic**

```bash
cd recipe-assistant/backend
alembic init alembic
```

- [ ] **Step 2: Edit `alembic.ini`**

Replace the `sqlalchemy.url` line:

```ini
sqlalchemy.url = postgresql+asyncpg://recipe:recipe@localhost:5432/recipe
```

- [ ] **Step 3: Replace `alembic/env.py` with async version**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.database import Base
from app.models import InventoryItem, StorageLocation, ChatMessage, InventoryLog  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_settings().database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(get_settings().database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Generate initial migration**

Requires a running Postgres instance. Start one if needed:
```bash
docker run -d --name recipe-pg -e POSTGRES_USER=recipe -e POSTGRES_PASSWORD=recipe -e POSTGRES_DB=recipe -p 5432:5432 postgres:16
```

Then generate:
```bash
cd recipe-assistant/backend
alembic revision --autogenerate -m "initial schema"
```

- [ ] **Step 5: Run migration**

```bash
cd recipe-assistant/backend
alembic upgrade head
```

Expected: Migration applies without errors.

- [ ] **Step 6: Verify tables exist**

```bash
docker exec recipe-pg psql -U recipe -c "\dt"
```

Expected: Tables `inventory`, `storage_locations`, `chat_history`, `inventory_log`, `alembic_version`.

- [ ] **Step 7: Commit**

```bash
git add recipe-assistant/backend/alembic.ini recipe-assistant/backend/alembic/
git commit -m "feat: add Alembic setup with initial migration"
```

---

## Task 6: Pydantic Schemas

**Files:**
- Create: `recipe-assistant/backend/app/schemas/inventory.py`
- Create: `recipe-assistant/backend/app/schemas/recipe.py`
- Create: `recipe-assistant/backend/app/schemas/chat.py`

- [ ] **Step 1: Create `schemas/inventory.py`**

```python
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class StorageLocationCreate(BaseModel):
    location_name: str


class StorageLocationResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class InventoryItemResponse(BaseModel):
    id: int
    barcode: str
    name: str
    quantity: int
    category: str
    storage_location: StorageLocationResponse | None = None
    expiration_date: date | None = None
    added_date: datetime
    updated_date: datetime

    model_config = {"from_attributes": True}


class BarcodeAddRequest(BaseModel):
    barcode: str
    storage_location: str | None = None
    expiration_date: date | None = None


class BarcodeRemoveRequest(BaseModel):
    barcode: str


class InventoryUpdateRequest(BaseModel):
    quantity: int | None = None
    storage_location: str | None = None
    expiration_date: date | None = None
```

- [ ] **Step 2: Create `schemas/recipe.py`**

```python
from __future__ import annotations

from pydantic import BaseModel


class Recipe(BaseModel):
    name: str
    short_description: str
    ingredients: list[str]
    instructions: str


class RecipeListResponse(BaseModel):
    recipes: list[Recipe]


class RecipeImageRequest(BaseModel):
    name: str
    generate_image: bool = True


class RecipeImageResponse(BaseModel):
    image_url: str | None = None
```

- [ ] **Step 3: Create `schemas/chat.py`**

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str
    use_ingredients: bool = False


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    response: str
    session_id: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]
    session_id: str
```

- [ ] **Step 4: Verify schemas import**

```bash
cd recipe-assistant/backend
python -c "from app.schemas.inventory import *; from app.schemas.recipe import *; from app.schemas.chat import *; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/schemas/
git commit -m "feat: add Pydantic request/response schemas"
```

---

## Task 7: Barcode Service + Tests

**Files:**
- Create: `recipe-assistant/backend/app/services/barcode.py`
- Create: `recipe-assistant/backend/tests/test_barcode.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_barcode.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from app.services.barcode import lookup_barcode


@pytest.mark.asyncio
async def test_lookup_barcode_found():
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": 1,
        "product": {
            "product_name": "Vollmilch",
            "categories": "Milchprodukte",
        },
    }

    with patch("app.services.barcode.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await lookup_barcode("4014400900057")

    assert result["name"] == "Vollmilch"
    assert result["category"] == "Milchprodukte"


@pytest.mark.asyncio
async def test_lookup_barcode_not_found():
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": 0}

    with patch("app.services.barcode.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await lookup_barcode("0000000000000")

    assert result["name"] == "Unbekanntes Produkt"
    assert result["category"] == "Unbekannt"


@pytest.mark.asyncio
async def test_lookup_barcode_timeout():
    import httpx

    with patch("app.services.barcode.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        result = await lookup_barcode("4014400900057")

    assert result["name"] == "Unbekanntes Produkt"
    assert result["category"] == "Unbekannt"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd recipe-assistant/backend
pytest tests/test_barcode.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.barcode'`

- [ ] **Step 3: Implement barcode service**

Create `app/services/barcode.py`:

```python
from __future__ import annotations

import httpx

OPENFOODFACTS_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
TIMEOUT_SECONDS = 5.0

FALLBACK = {"name": "Unbekanntes Produkt", "category": "Unbekannt"}


async def lookup_barcode(barcode: str) -> dict[str, str]:
    """Look up a barcode on OpenFoodFacts. Returns dict with 'name' and 'category'."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(OPENFOODFACTS_URL.format(barcode=barcode))
            data = response.json()

        if data.get("status") != 1:
            return FALLBACK

        product = data.get("product", {})
        return {
            "name": product.get("product_name") or FALLBACK["name"],
            "category": product.get("categories") or FALLBACK["category"],
        }
    except (httpx.TimeoutException, httpx.HTTPError):
        return FALLBACK
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd recipe-assistant/backend
pytest tests/test_barcode.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/barcode.py recipe-assistant/backend/tests/test_barcode.py
git commit -m "feat: add barcode lookup service with OpenFoodFacts"
```

---

## Task 8: Test Fixtures + Inventory Router

**Files:**
- Create: `recipe-assistant/backend/tests/conftest.py`
- Create: `recipe-assistant/backend/app/routers/inventory.py`
- Create: `recipe-assistant/backend/tests/test_inventory.py`

- [ ] **Step 1: Create test fixtures in `conftest.py`**

```python
import asyncio
from collections.abc import AsyncGenerator

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


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

- [ ] **Step 2: Write failing inventory tests**

Create `tests/test_inventory.py`:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_inventory_empty(client: AsyncClient):
    response = await client.get("/api/inventory/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_add_item_by_barcode(client: AsyncClient):
    response = await client.post(
        "/api/inventory/barcode",
        json={"barcode": "4014400900057", "storage_location": None},
    )
    assert response.status_code == 201
    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_add_duplicate_barcode_increments_quantity(client: AsyncClient):
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "1234567890123"},
    )
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "1234567890123"},
    )
    response = await client.get("/api/inventory/")
    items = response.json()
    matching = [i for i in items if i["barcode"] == "1234567890123"]
    assert len(matching) == 1
    assert matching[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_update_item_quantity(client: AsyncClient):
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "1111111111111"},
    )
    response = await client.put(
        "/api/inventory/1111111111111",
        json={"quantity": 5},
    )
    assert response.status_code == 200

    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "1111111111111"]
    assert matching[0]["quantity"] == 5


@pytest.mark.asyncio
async def test_update_quantity_to_zero_deletes(client: AsyncClient):
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "2222222222222"},
    )
    response = await client.put(
        "/api/inventory/2222222222222",
        json={"quantity": 0},
    )
    assert response.status_code == 200

    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "2222222222222"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient):
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "3333333333333"},
    )
    response = await client.delete("/api/inventory/3333333333333")
    assert response.status_code == 200

    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "3333333333333"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_remove_decrements_quantity(client: AsyncClient):
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "4444444444444"},
    )
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "4444444444444"},
    )
    response = await client.post(
        "/api/inventory/remove",
        json={"barcode": "4444444444444"},
    )
    assert response.status_code == 200

    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "4444444444444"]
    assert matching[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_remove_last_item_deletes(client: AsyncClient):
    await client.post(
        "/api/inventory/barcode",
        json={"barcode": "5555555555555"},
    )
    response = await client.post(
        "/api/inventory/remove",
        json={"barcode": "5555555555555"},
    )
    assert response.status_code == 200

    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "5555555555555"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client: AsyncClient):
    response = await client.delete("/api/inventory/9999999999999")
    assert response.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd recipe-assistant/backend
pytest tests/test_inventory.py -v
```

Expected: FAIL — needs `app.main` and `/api/inventory` router.

- [ ] **Step 4: Create minimal `app/main.py`**

```python
from fastapi import FastAPI

from app.routers import inventory, storage, assistant

app = FastAPI(title="Recipe Assistant API", version="2.0.0")

app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(storage.router, prefix="/api/storage-locations", tags=["storage"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])
```

- [ ] **Step 5: Create stub routers for storage and assistant**

Create `app/routers/storage.py`:
```python
from fastapi import APIRouter

router = APIRouter()
```

Create `app/routers/assistant.py`:
```python
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 6: Implement `app/routers/inventory.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.inventory import InventoryItem, StorageLocation
from app.models.log import InventoryLog
from app.schemas.inventory import (
    BarcodeAddRequest,
    BarcodeRemoveRequest,
    InventoryItemResponse,
    InventoryUpdateRequest,
)
from app.services.barcode import lookup_barcode

router = APIRouter()


async def _log_action(db: AsyncSession, barcode: str, action: str, details: str | None = None) -> None:
    db.add(InventoryLog(barcode=barcode, action=action, details=details))


async def _resolve_storage_location(db: AsyncSession, name: str | None) -> int | None:
    if not name:
        return None
    result = await db.execute(select(StorageLocation).where(StorageLocation.name == name))
    location = result.scalar_one_or_none()
    if location:
        return location.id
    new_loc = StorageLocation(name=name)
    db.add(new_loc)
    await db.flush()
    return new_loc.id


@router.get("/", response_model=list[InventoryItemResponse])
async def get_inventory(
    search: str | None = None,
    sort_by: str = "name",
    order: str = "asc",
    db: AsyncSession = Depends(get_db),
):
    query = select(InventoryItem).options(selectinload(InventoryItem.storage_location))

    if search:
        query = query.where(
            InventoryItem.name.ilike(f"%{search}%")
            | InventoryItem.category.ilike(f"%{search}%")
        )

    allowed_sort = {"name", "quantity", "category", "added_date", "barcode"}
    if sort_by in allowed_sort:
        col = getattr(InventoryItem, sort_by)
        query = query.order_by(col.desc() if order == "desc" else col.asc())

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/barcode", status_code=201)
async def add_item_by_barcode(
    req: BarcodeAddRequest,
    db: AsyncSession = Depends(get_db),
):
    product = await lookup_barcode(req.barcode)
    location_id = await _resolve_storage_location(db, req.storage_location)

    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == req.barcode)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity += 1
        await _log_action(db, req.barcode, "add", f"quantity: {existing.quantity - 1} → {existing.quantity}")
        await db.commit()
        return {"message": f'Produkt "{existing.name}" existierte bereits. Menge um 1 erhöht.'}

    item = InventoryItem(
        barcode=req.barcode,
        name=product["name"],
        quantity=1,
        category=product["category"],
        storage_location_id=location_id,
        expiration_date=req.expiration_date,
    )
    db.add(item)
    await _log_action(db, req.barcode, "add")
    await db.commit()
    return {"message": f'Artikel "{product["name"]}" hinzugefügt!'}


@router.post("/remove")
async def remove_item_by_barcode(
    req: BarcodeRemoveRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == req.barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Kein Artikel mit Barcode {req.barcode} gefunden")

    if item.quantity > 1:
        old_qty = item.quantity
        item.quantity -= 1
        await _log_action(db, req.barcode, "remove", f"quantity: {old_qty} → {item.quantity}")
        await db.commit()
        return {"message": f"Produkt um 1 reduziert. Verbleibend: {item.quantity}"}

    await _log_action(db, req.barcode, "delete", "removed last item")
    await db.delete(item)
    await db.commit()
    return {"message": f"Produkt mit Barcode {req.barcode} wurde entfernt."}


@router.put("/{barcode}")
async def update_item(
    barcode: str,
    req: InventoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Kein Artikel mit Barcode {barcode} gefunden")

    if req.quantity is not None:
        if req.quantity == 0:
            await _log_action(db, barcode, "delete", "quantity set to 0")
            await db.delete(item)
            await db.commit()
            return {"message": f"Artikel mit Barcode {barcode} wurde gelöscht."}
        old_qty = item.quantity
        item.quantity = req.quantity
        await _log_action(db, barcode, "update", f"quantity: {old_qty} → {req.quantity}")

    if req.storage_location is not None:
        item.storage_location_id = await _resolve_storage_location(db, req.storage_location)

    if req.expiration_date is not None:
        item.expiration_date = req.expiration_date

    await db.commit()
    return {"message": f"Artikel mit Barcode {barcode} aktualisiert."}


@router.delete("/{barcode}")
async def delete_item(
    barcode: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.barcode == barcode)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"Kein Artikel mit Barcode {barcode} gefunden")

    await _log_action(db, barcode, "delete")
    await db.delete(item)
    await db.commit()
    return {"message": f"Artikel mit Barcode {barcode} wurde gelöscht."}
```

- [ ] **Step 7: Run inventory tests**

```bash
cd recipe-assistant/backend
pytest tests/test_inventory.py -v
```

Expected: All 9 tests pass. (The `add_item_by_barcode` test calls OpenFoodFacts — mock it if needed, or accept the fallback "Unbekanntes Produkt" name for test purposes since httpx will likely timeout in test.)

- [ ] **Step 8: Commit**

```bash
git add recipe-assistant/backend/tests/ recipe-assistant/backend/app/routers/ recipe-assistant/backend/app/main.py
git commit -m "feat: add inventory router with full CRUD + tests"
```

---

## Task 9: Storage Locations Router + Tests

**Files:**
- Modify: `recipe-assistant/backend/app/routers/storage.py`
- Create: `recipe-assistant/backend/tests/test_storage.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_storage.py`:

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_locations_empty(client: AsyncClient):
    response = await client.get("/api/storage-locations/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_location(client: AsyncClient):
    response = await client.post(
        "/api/storage-locations/",
        json={"location_name": "Kühlschrank"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Kühlschrank"


@pytest.mark.asyncio
async def test_create_duplicate_location(client: AsyncClient):
    await client.post("/api/storage-locations/", json={"location_name": "Keller"})
    response = await client.post("/api/storage-locations/", json={"location_name": "Keller"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_location(client: AsyncClient):
    resp = await client.post("/api/storage-locations/", json={"location_name": "Garage"})
    loc_id = resp.json()["id"]

    response = await client.delete(f"/api/storage-locations/{loc_id}")
    assert response.status_code == 200

    locations = await client.get("/api/storage-locations/")
    assert all(loc["name"] != "Garage" for loc in locations.json())


@pytest.mark.asyncio
async def test_delete_nonexistent_location(client: AsyncClient):
    response = await client.delete("/api/storage-locations/99999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd recipe-assistant/backend
pytest tests/test_storage.py -v
```

Expected: FAIL — empty router has no endpoints.

- [ ] **Step 3: Implement storage router**

Replace `app/routers/storage.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inventory import StorageLocation
from app.schemas.inventory import StorageLocationCreate, StorageLocationResponse

router = APIRouter()


@router.get("/", response_model=list[StorageLocationResponse])
async def get_storage_locations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StorageLocation).order_by(StorageLocation.name))
    return result.scalars().all()


@router.post("/", response_model=StorageLocationResponse, status_code=201)
async def create_storage_location(
    req: StorageLocationCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StorageLocation).where(StorageLocation.name == req.location_name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f'Lagerort "{req.location_name}" existiert bereits.')

    location = StorageLocation(name=req.location_name)
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


@router.delete("/{location_id}")
async def delete_storage_location(
    location_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StorageLocation).where(StorageLocation.id == location_id)
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Lagerort nicht gefunden")

    await db.delete(location)
    await db.commit()
    return {"message": f'Lagerort "{location.name}" gelöscht.'}
```

- [ ] **Step 4: Run tests**

```bash
cd recipe-assistant/backend
pytest tests/test_storage.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/routers/storage.py recipe-assistant/backend/tests/test_storage.py
git commit -m "feat: add storage locations router with CRUD + tests"
```

---

## Task 10: AI Services (Claude Chat + Recipes, DALL-E Images)

**Files:**
- Create: `recipe-assistant/backend/app/services/ai_chat.py`
- Create: `recipe-assistant/backend/app/services/ai_recipes.py`
- Create: `recipe-assistant/backend/app/services/ai_images.py`
- Create: `recipe-assistant/backend/tests/test_assistant.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_assistant.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_chat_service_returns_response():
    from app.services.ai_chat import get_chat_response

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Hier ist ein Rezept für Pfannkuchen.")]
    mock_response = MagicMock(content=[MagicMock(text="Hier ist ein Rezept für Pfannkuchen.")])

    with patch("app.services.ai_chat.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await get_chat_response(
            messages=[{"role": "user", "content": "Was kann ich mit Mehl machen?"}],
            system_prompt="Du bist ein Kochassistent.",
        )

    assert "Pfannkuchen" in result


@pytest.mark.asyncio
async def test_recipe_service_returns_recipes():
    from app.services.ai_recipes import get_recipe_suggestions

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            type="tool_use",
            input={
                "recipes": [
                    {
                        "name": "Pfannkuchen",
                        "short_description": "Einfache Pfannkuchen",
                        "ingredients": ["Mehl", "Milch", "Eier"],
                        "instructions": "Alles verrühren und braten.",
                    }
                ]
            },
        )
    ]

    with patch("app.services.ai_recipes.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await get_recipe_suggestions(["Mehl", "Milch", "Eier"])

    assert len(result) == 1
    assert result[0].name == "Pfannkuchen"


@pytest.mark.asyncio
async def test_image_service_returns_url():
    from app.services.ai_images import generate_recipe_image

    mock_image = MagicMock()
    mock_image.data = [MagicMock(url="https://example.com/image.png")]

    with patch("app.services.ai_images.openai_client") as mock_client:
        mock_client.images.generate = AsyncMock(return_value=mock_image)
        result = await generate_recipe_image("Pfannkuchen")

    assert result == "https://example.com/image.png"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd recipe-assistant/backend
pytest tests/test_assistant.py -v
```

Expected: FAIL — modules don't exist yet.

- [ ] **Step 3: Implement `app/services/ai_chat.py`**

```python
from __future__ import annotations

import anthropic

from app.config import get_settings

settings = get_settings()
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

DEFAULT_SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Kochassistent. Du antwortest auf Deutsch und hilfst "
    "beim Kochen, bei Rezepten und bei Fragen rund um Lebensmittel."
)


async def get_chat_response(
    messages: list[dict[str, str]],
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> str:
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text
```

- [ ] **Step 4: Implement `app/services/ai_recipes.py`**

```python
from __future__ import annotations

import anthropic

from app.config import get_settings
from app.schemas.recipe import Recipe

settings = get_settings()
client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

RECIPE_TOOL = {
    "name": "return_recipes",
    "description": "Return a list of recipe suggestions based on available ingredients.",
    "input_schema": {
        "type": "object",
        "properties": {
            "recipes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name des Rezepts"},
                        "short_description": {"type": "string", "description": "Kurzbeschreibung"},
                        "ingredients": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Liste der Zutaten mit Mengenangaben",
                        },
                        "instructions": {"type": "string", "description": "Zubereitungsanleitung als Markdown"},
                    },
                    "required": ["name", "short_description", "ingredients", "instructions"],
                },
                "description": "Liste von 5 Rezeptvorschlägen",
            }
        },
        "required": ["recipes"],
    },
}


async def get_recipe_suggestions(ingredients: list[str]) -> list[Recipe]:
    ingredients_str = ", ".join(ingredients)

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="Du bist ein Kochassistent. Antworte nur über das Tool.",
        messages=[
            {
                "role": "user",
                "content": (
                    f"Ich habe folgende Zutaten: {ingredients_str}. "
                    "Bitte erstelle eine Liste von 5 Rezepten mit diesen Zutaten. "
                    "Nutze das return_recipes Tool."
                ),
            }
        ],
        tools=[RECIPE_TOOL],
        tool_choice={"type": "tool", "name": "return_recipes"},
    )

    for block in response.content:
        if block.type == "tool_use":
            return [Recipe(**r) for r in block.input["recipes"]]

    return []
```

- [ ] **Step 5: Implement `app/services/ai_images.py`**

```python
from __future__ import annotations

from openai import AsyncOpenAI

from app.config import get_settings

settings = get_settings()
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def generate_recipe_image(recipe_name: str) -> str | None:
    response = await openai_client.images.generate(
        model="dall-e-3",
        prompt=(
            f"Ein realistisches Bild von '{recipe_name}', ein leckeres Gericht. "
            "Hochwertige Food-Fotografie, ästhetisch angerichtet."
        ),
        n=1,
        size="1024x1024",
    )
    return response.data[0].url
```

- [ ] **Step 6: Run tests**

```bash
cd recipe-assistant/backend
pytest tests/test_assistant.py -v
```

Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add recipe-assistant/backend/app/services/ai_chat.py recipe-assistant/backend/app/services/ai_recipes.py recipe-assistant/backend/app/services/ai_images.py recipe-assistant/backend/tests/test_assistant.py
git commit -m "feat: add AI services - Claude chat/recipes + DALL-E images"
```

---

## Task 11: Assistant Router

**Files:**
- Modify: `recipe-assistant/backend/app/routers/assistant.py`

- [ ] **Step 1: Implement assistant router**

Replace `app/routers/assistant.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat import ChatMessage
from app.models.inventory import InventoryItem
from app.schemas.chat import ChatHistoryResponse, ChatMessageResponse, ChatRequest, ChatResponse
from app.schemas.recipe import RecipeImageRequest, RecipeImageResponse, RecipeListResponse
from app.services.ai_chat import get_chat_response
from app.services.ai_images import generate_recipe_image
from app.services.ai_recipes import get_recipe_suggestions

router = APIRouter()


@router.get("/recipes", response_model=RecipeListResponse)
async def recipe_suggestions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InventoryItem.name).where(InventoryItem.quantity > 0)
    )
    ingredients = [row[0] for row in result.all()]

    if not ingredients:
        raise HTTPException(status_code=400, detail="Keine Lebensmittel im Inventar gefunden.")

    recipes = await get_recipe_suggestions(ingredients)
    return RecipeListResponse(recipes=recipes)


@router.post("/recipe-image", response_model=RecipeImageResponse)
async def recipe_image(req: RecipeImageRequest):
    if not req.generate_image:
        return RecipeImageResponse(image_url=None)

    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Kein Rezeptname angegeben.")

    url = await generate_recipe_image(req.name)
    return RecipeImageResponse(image_url=url)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Leere Nachricht kann nicht verarbeitet werden.")

    session_id = req.session_id or str(uuid.uuid4())

    # Load existing chat history for this session
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
    )
    history_rows = result.scalars().all()
    messages: list[dict[str, str]] = [{"role": m.role, "content": m.content} for m in history_rows]

    # If first message and use_ingredients, add inventory context as system prefix
    system_suffix = ""
    if not messages and req.use_ingredients:
        inv_result = await db.execute(
            select(InventoryItem.name).where(InventoryItem.quantity > 0)
        )
        ingredients = [row[0] for row in inv_result.all()]
        if ingredients:
            system_suffix = f"\n\nDer Nutzer hat folgende Zutaten im Haushalt: {', '.join(ingredients)}."

    messages.append({"role": "user", "content": req.message})

    system_prompt = "Du bist ein hilfreicher Kochassistent. Du antwortest auf Deutsch."
    if system_suffix:
        system_prompt += system_suffix

    ai_response = await get_chat_response(messages=messages, system_prompt=system_prompt)

    # Save user message + AI response to DB
    db.add(ChatMessage(session_id=session_id, role="user", content=req.message))
    db.add(ChatMessage(session_id=session_id, role="assistant", content=ai_response))
    await db.commit()

    return ChatResponse(response=ai_response, session_id=session_id)


@router.post("/chat/clear/{session_id}")
async def clear_chat(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    messages = result.scalars().all()
    for msg in messages:
        await db.delete(msg)
    await db.commit()
    return {"message": "Chatverlauf wurde gelöscht."}


@router.get("/chat/history/{session_id}", response_model=ChatHistoryResponse)
async def chat_history(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
    )
    messages = result.scalars().all()
    return ChatHistoryResponse(
        messages=[ChatMessageResponse.model_validate(m) for m in messages],
        session_id=session_id,
    )
```

- [ ] **Step 2: Run full backend test suite**

```bash
cd recipe-assistant/backend
pytest -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/app/routers/assistant.py
git commit -m "feat: add assistant router with chat, recipes, and image endpoints"
```

---

## Task 12: Frontend Scaffolding

**Files:**
- Create: `recipe-assistant/frontend/package.json`
- Create: `recipe-assistant/frontend/vite.config.ts`
- Create: `recipe-assistant/frontend/tsconfig.json`
- Create: `recipe-assistant/frontend/tsconfig.node.json`
- Create: `recipe-assistant/frontend/index.html`
- Create: `recipe-assistant/frontend/src/main.tsx`

- [ ] **Step 1: Remove old frontend**

```bash
rm -rf recipe-assistant/frontend/src recipe-assistant/frontend/public recipe-assistant/frontend/package.json recipe-assistant/frontend/package-lock.json
```

- [ ] **Step 2: Create `package.json`**

```json
{
  "name": "recipe-assistant-frontend",
  "private": true,
  "version": "2.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@emotion/react": "^11.14.0",
    "@emotion/styled": "^11.14.0",
    "@mui/material": "^6.4.7",
    "@mui/icons-material": "^6.4.7",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.3.0",
    "react-markdown": "^10.1.0",
    "react-zxing": "^2.0.2",
    "remark-gfm": "^4.0.1"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.7.0",
    "vite": "^6.2.0"
  }
}
```

- [ ] **Step 3: Create `vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "build",
  },
});
```

- [ ] **Step 4: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

- [ ] **Step 5: Create `tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: Create `index.html`**

```html
<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Recipe Assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create `src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import App from "./App";

const theme = createTheme({
  palette: {
    primary: { main: "#1976d2" },
    secondary: { main: "#d32f2f" },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
```

- [ ] **Step 8: Create stub `src/App.tsx`**

```tsx
const App = () => <div>Recipe Assistant v2</div>;
export default App;
```

- [ ] **Step 9: Install and verify**

```bash
cd recipe-assistant/frontend
npm install
npm run build
```

Expected: Build succeeds, output in `build/`.

- [ ] **Step 10: Commit**

```bash
git add recipe-assistant/frontend/
git commit -m "feat: scaffold frontend with Vite + TypeScript + MUI"
```

---

## Task 13: Frontend Types + API Client

**Files:**
- Create: `recipe-assistant/frontend/src/types/index.ts`
- Create: `recipe-assistant/frontend/src/api/client.ts`

- [ ] **Step 1: Create `types/index.ts`**

```typescript
export interface StorageLocation {
  id: number;
  name: string;
}

export interface InventoryItem {
  id: number;
  barcode: string;
  name: string;
  quantity: number;
  category: string;
  storage_location: StorageLocation | null;
  expiration_date: string | null;
  added_date: string;
  updated_date: string;
}

export interface Recipe {
  name: string;
  short_description: string;
  ingredients: string[];
  instructions: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}
```

- [ ] **Step 2: Create `api/client.ts`**

```typescript
import type {
  InventoryItem,
  StorageLocation,
  Recipe,
  ChatMessage,
} from "../types";

const BASE = "/api";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unbekannter Fehler" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

// Inventory
export const getInventory = (search?: string, sortBy?: string, order?: string) => {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (sortBy) params.set("sort_by", sortBy);
  if (order) params.set("order", order);
  const qs = params.toString();
  return request<InventoryItem[]>(`/inventory/${qs ? `?${qs}` : ""}`);
};

export const addItemByBarcode = (barcode: string, storageLocation?: string, expirationDate?: string) =>
  request<{ message: string }>("/inventory/barcode", {
    method: "POST",
    body: JSON.stringify({
      barcode,
      storage_location: storageLocation || null,
      expiration_date: expirationDate || null,
    }),
  });

export const removeItemByBarcode = (barcode: string) =>
  request<{ message: string }>("/inventory/remove", {
    method: "POST",
    body: JSON.stringify({ barcode }),
  });

export const updateItem = (barcode: string, data: {
  quantity?: number;
  storage_location?: string;
  expiration_date?: string;
}) =>
  request<{ message: string }>(`/inventory/${barcode}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteItem = (barcode: string) =>
  request<{ message: string }>(`/inventory/${barcode}`, { method: "DELETE" });

// Storage Locations
export const getStorageLocations = () =>
  request<StorageLocation[]>("/storage-locations/");

export const createStorageLocation = (name: string) =>
  request<StorageLocation>("/storage-locations/", {
    method: "POST",
    body: JSON.stringify({ location_name: name }),
  });

export const deleteStorageLocation = (id: number) =>
  request<{ message: string }>(`/storage-locations/${id}`, { method: "DELETE" });

// Assistant
export const getRecipeSuggestions = () =>
  request<{ recipes: Recipe[] }>("/assistant/recipes");

export const generateRecipeImage = (name: string) =>
  request<{ image_url: string | null }>("/assistant/recipe-image", {
    method: "POST",
    body: JSON.stringify({ name, generate_image: true }),
  });

export const sendChatMessage = (message: string, sessionId: string, useIngredients: boolean) =>
  request<{ response: string; session_id: string }>("/assistant/chat", {
    method: "POST",
    body: JSON.stringify({ message, session_id: sessionId, use_ingredients: useIngredients }),
  });

export const clearChat = (sessionId: string) =>
  request<{ message: string }>(`/assistant/chat/clear/${sessionId}`, { method: "POST" });

export const getChatHistory = (sessionId: string) =>
  request<{ messages: ChatMessage[]; session_id: string }>(
    `/assistant/chat/history/${sessionId}`
  );
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd recipe-assistant/frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/types/ recipe-assistant/frontend/src/api/
git commit -m "feat: add TypeScript types and central API client"
```

---

## Task 14: NotificationProvider + Navbar + App Router

**Files:**
- Create: `recipe-assistant/frontend/src/components/NotificationProvider.tsx`
- Create: `recipe-assistant/frontend/src/components/Navbar.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`

- [ ] **Step 1: Create `NotificationProvider.tsx`**

```tsx
import React, { createContext, useCallback, useContext, useState } from "react";
import { Alert, Snackbar } from "@mui/material";

type Severity = "success" | "error" | "warning" | "info";

interface NotificationContextType {
  notify: (message: string, severity?: Severity) => void;
}

const NotificationContext = createContext<NotificationContextType>({
  notify: () => {},
});

export const useNotification = () => useContext(NotificationContext);

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [severity, setSeverity] = useState<Severity>("info");

  const notify = useCallback((msg: string, sev: Severity = "info") => {
    setMessage(msg);
    setSeverity(sev);
    setOpen(true);
  }, []);

  return (
    <NotificationContext.Provider value={{ notify }}>
      {children}
      <Snackbar
        open={open}
        autoHideDuration={3000}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert onClose={() => setOpen(false)} severity={severity} sx={{ width: "100%" }}>
          {message}
        </Alert>
      </Snackbar>
    </NotificationContext.Provider>
  );
};
```

- [ ] **Step 2: Create `Navbar.tsx`**

```tsx
import { AppBar, Button, Toolbar, Typography } from "@mui/material";
import { Link } from "react-router-dom";

const Navbar = () => (
  <AppBar position="static">
    <Toolbar>
      <Typography variant="h6" sx={{ flexGrow: 1 }}>
        Inventar & Assistent
      </Typography>
      <Button color="inherit" component={Link} to="/">
        Inventar
      </Button>
      <Button color="inherit" component={Link} to="/scan">
        Scannen
      </Button>
      <Button color="inherit" component={Link} to="/scan-station">
        Scan-Station
      </Button>
      <Button color="inherit" component={Link} to="/recipes">
        Rezepte
      </Button>
      <Button color="inherit" component={Link} to="/chat">
        Chat
      </Button>
    </Toolbar>
  </AppBar>
);

export default Navbar;
```

- [ ] **Step 3: Update `App.tsx` with router**

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { NotificationProvider } from "./components/NotificationProvider";
import Navbar from "./components/Navbar";

// Placeholder pages until implemented
const Placeholder = ({ name }: { name: string }) => (
  <div style={{ padding: 24 }}>{name} - Coming Soon</div>
);

const App = () => (
  <BrowserRouter>
    <NotificationProvider>
      <Navbar />
      <Routes>
        <Route path="/" element={<Placeholder name="Inventar" />} />
        <Route path="/scan" element={<Placeholder name="Scannen" />} />
        <Route path="/scan-station" element={<Placeholder name="Scan-Station" />} />
        <Route path="/recipes" element={<Placeholder name="Rezepte" />} />
        <Route path="/chat" element={<Placeholder name="Chat" />} />
      </Routes>
    </NotificationProvider>
  </BrowserRouter>
);

export default App;
```

- [ ] **Step 4: Verify build**

```bash
cd recipe-assistant/frontend
npx tsc --noEmit && npm run build
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/
git commit -m "feat: add NotificationProvider, Navbar, and App router shell"
```

---

## Task 15: useInventory Hook + InventoryPage

**Files:**
- Create: `recipe-assistant/frontend/src/hooks/useInventory.ts`
- Create: `recipe-assistant/frontend/src/pages/InventoryPage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`

- [ ] **Step 1: Create `useInventory.ts`**

```typescript
import { useCallback, useEffect, useState } from "react";
import type { InventoryItem } from "../types";
import {
  getInventory,
  updateItem,
  deleteItem,
  addItemByBarcode,
  removeItemByBarcode,
} from "../api/client";

export function useInventory() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async (search?: string, sortBy?: string, order?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getInventory(search, sortBy, order);
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Laden");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const add = async (barcode: string, storageLocation?: string, expirationDate?: string) => {
    const result = await addItemByBarcode(barcode, storageLocation, expirationDate);
    await fetch();
    return result;
  };

  const remove = async (barcode: string) => {
    const result = await removeItemByBarcode(barcode);
    await fetch();
    return result;
  };

  const update = async (barcode: string, data: Parameters<typeof updateItem>[1]) => {
    const result = await updateItem(barcode, data);
    await fetch();
    return result;
  };

  const del = async (barcode: string) => {
    const result = await deleteItem(barcode);
    await fetch();
    return result;
  };

  return { items, loading, error, refetch: fetch, add, remove, update, delete: del };
}
```

- [ ] **Step 2: Create `InventoryPage.tsx`**

```tsx
import { useState } from "react";
import {
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Typography,
} from "@mui/material";
import { useInventory } from "../hooks/useInventory";
import { useNotification } from "../components/NotificationProvider";

type SortKey = "name" | "quantity" | "category" | "barcode" | "added_date";
type Order = "asc" | "desc";

const InventoryPage = () => {
  const inventory = useInventory();
  const { items, loading, refetch } = inventory;
  const { notify } = useNotification();
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("name");
  const [order, setOrder] = useState<Order>("asc");
  const [editFields, setEditFields] = useState<
    Record<number, { quantity?: string; storage_location?: string; expiration_date?: string }>
  >({});

  const handleSort = (key: SortKey) => {
    const newOrder = sortBy === key && order === "asc" ? "desc" : "asc";
    setSortBy(key);
    setOrder(newOrder);
    refetch(search, key, newOrder);
  };

  const handleSearch = (value: string) => {
    setSearch(value);
    refetch(value, sortBy, order);
  };

  const handleFieldChange = (id: number, field: string, value: string) => {
    setEditFields((prev) => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }));
  };

  const handleUpdate = async (id: number, barcode: string) => {
    const fields = editFields[id];
    if (!fields) return;

    try {
      const updateData: { quantity?: number; storage_location?: string; expiration_date?: string } = {};
      if (fields.quantity !== undefined) {
        const qty = parseInt(fields.quantity, 10);
        if (isNaN(qty) || qty < 0) return;
        if (qty === 0 && !window.confirm("Artikel wirklich löschen?")) return;
        updateData.quantity = qty;
      }
      if (fields.storage_location !== undefined) updateData.storage_location = fields.storage_location;
      if (fields.expiration_date !== undefined) updateData.expiration_date = fields.expiration_date;

      const result = await inventory.update(barcode, updateData);
      notify(result.message, "success");
      setEditFields((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Aktualisieren", "error");
    }
  };

  const handleDelete = async (barcode: string) => {
    if (!window.confirm("Artikel wirklich löschen?")) return;
    try {
      const result = await inventory.delete(barcode);
      notify(result.message, "success");
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler beim Löschen", "error");
    }
  };

  const columns: { key: SortKey; label: string }[] = [
    { key: "name", label: "Name" },
    { key: "barcode", label: "Barcode" },
    { key: "quantity", label: "Menge" },
    { key: "category", label: "Kategorie" },
    { key: "added_date", label: "Hinzugefügt" },
  ];

  return (
    <Paper sx={{ p: 2, m: 2 }}>
      <Typography variant="h4" gutterBottom>
        Inventarverwaltung
      </Typography>
      <TextField
        label="Suche nach Name oder Kategorie"
        variant="outlined"
        fullWidth
        margin="normal"
        value={search}
        onChange={(e) => handleSearch(e.target.value)}
      />
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              {columns.map((col) => (
                <TableCell key={col.key}>
                  <TableSortLabel
                    active={sortBy === col.key}
                    direction={sortBy === col.key ? order : "asc"}
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                  </TableSortLabel>
                </TableCell>
              ))}
              <TableCell>Lagerort</TableCell>
              <TableCell>Ablaufdatum</TableCell>
              <TableCell>Aktionen</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.name}</TableCell>
                <TableCell>{item.barcode}</TableCell>
                <TableCell>
                  <TextField
                    type="number"
                    size="small"
                    sx={{ width: 80 }}
                    value={editFields[item.id]?.quantity ?? item.quantity}
                    onChange={(e) => handleFieldChange(item.id, "quantity", e.target.value)}
                  />
                </TableCell>
                <TableCell>{item.category}</TableCell>
                <TableCell>{new Date(item.added_date).toLocaleDateString("de-DE")}</TableCell>
                <TableCell>
                  <TextField
                    size="small"
                    sx={{ width: 130 }}
                    value={
                      editFields[item.id]?.storage_location ??
                      item.storage_location?.name ??
                      ""
                    }
                    onChange={(e) =>
                      handleFieldChange(item.id, "storage_location", e.target.value)
                    }
                  />
                </TableCell>
                <TableCell>
                  <TextField
                    type="date"
                    size="small"
                    sx={{ width: 150 }}
                    InputLabelProps={{ shrink: true }}
                    value={editFields[item.id]?.expiration_date ?? item.expiration_date ?? ""}
                    onChange={(e) =>
                      handleFieldChange(item.id, "expiration_date", e.target.value)
                    }
                  />
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Button
                    variant="contained"
                    size="small"
                    sx={{ mr: 1 }}
                    onClick={() => handleUpdate(item.id, item.barcode)}
                    disabled={!editFields[item.id]}
                  >
                    Speichern
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    size="small"
                    onClick={() => handleDelete(item.barcode)}
                  >
                    Löschen
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!loading && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  Keine Artikel gefunden.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default InventoryPage;
```

- [ ] **Step 3: Update `App.tsx` to use InventoryPage**

Replace the `"/"` route placeholder:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { NotificationProvider } from "./components/NotificationProvider";
import Navbar from "./components/Navbar";
import InventoryPage from "./pages/InventoryPage";

const Placeholder = ({ name }: { name: string }) => (
  <div style={{ padding: 24 }}>{name} - Coming Soon</div>
);

const App = () => (
  <BrowserRouter>
    <NotificationProvider>
      <Navbar />
      <Routes>
        <Route path="/" element={<InventoryPage />} />
        <Route path="/scan" element={<Placeholder name="Scannen" />} />
        <Route path="/scan-station" element={<Placeholder name="Scan-Station" />} />
        <Route path="/recipes" element={<Placeholder name="Rezepte" />} />
        <Route path="/chat" element={<Placeholder name="Chat" />} />
      </Routes>
    </NotificationProvider>
  </BrowserRouter>
);

export default App;
```

- [ ] **Step 4: Verify build**

```bash
cd recipe-assistant/frontend
npx tsc --noEmit && npm run build
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/
git commit -m "feat: add useInventory hook and InventoryPage with inline editing"
```

---

## Task 16: useScanner Hook + ScanPage

**Files:**
- Create: `recipe-assistant/frontend/src/hooks/useScanner.ts`
- Create: `recipe-assistant/frontend/src/pages/ScanPage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`

- [ ] **Step 1: Create `useScanner.ts`**

```typescript
import { useCallback, useRef, useState } from "react";

interface UseScannerOptions {
  onScan: (barcode: string) => void;
  cooldownMs?: number;
}

export function useScanner({ onScan, cooldownMs = 2000 }: UseScannerOptions) {
  const [lastScanned, setLastScanned] = useState<string | null>(null);
  const cooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastBarcodeRef = useRef<string | null>(null);

  const handleDecode = useCallback(
    (result: string) => {
      const barcode = result.trim();
      if (!barcode) return;

      // Prevent duplicate scans within cooldown
      if (barcode === lastBarcodeRef.current && cooldownRef.current) return;

      lastBarcodeRef.current = barcode;
      setLastScanned(barcode);
      onScan(barcode);

      if (cooldownRef.current) clearTimeout(cooldownRef.current);
      cooldownRef.current = setTimeout(() => {
        cooldownRef.current = null;
        lastBarcodeRef.current = null;
      }, cooldownMs);
    },
    [onScan, cooldownMs]
  );

  return { lastScanned, handleDecode };
}
```

- [ ] **Step 2: Create `ScanPage.tsx`**

```tsx
import { useState } from "react";
import {
  Button,
  FormControl,
  FormControlLabel,
  FormLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  TextField,
  Typography,
} from "@mui/material";
import { useZxing } from "react-zxing";
import { useScanner } from "../hooks/useScanner";
import { useNotification } from "../components/NotificationProvider";
import { addItemByBarcode, removeItemByBarcode, getStorageLocations, createStorageLocation } from "../api/client";
import { useEffect } from "react";
import type { StorageLocation } from "../types";

const ScanPage = () => {
  const { notify } = useNotification();
  const [mode, setMode] = useState<"add" | "remove">("add");
  const [manualBarcode, setManualBarcode] = useState("");
  const [locations, setLocations] = useState<StorageLocation[]>([]);
  const [selectedLocation, setSelectedLocation] = useState("");
  const [newLocation, setNewLocation] = useState("");
  const [expirationDate, setExpirationDate] = useState("");

  useEffect(() => {
    getStorageLocations().then(setLocations).catch(() => {});
  }, []);

  const processBarcode = async (barcode: string) => {
    try {
      if (mode === "add") {
        const location = newLocation.trim() || selectedLocation;
        if (newLocation.trim()) {
          await createStorageLocation(newLocation.trim());
          const updated = await getStorageLocations();
          setLocations(updated);
          setNewLocation("");
        }
        const result = await addItemByBarcode(barcode, location, expirationDate || undefined);
        notify(result.message, "success");
      } else {
        const result = await removeItemByBarcode(barcode);
        notify(result.message, "success");
      }
    } catch (e) {
      notify(e instanceof Error ? e.message : "Fehler", "error");
    }
  };

  const { lastScanned, handleDecode } = useScanner({ onScan: processBarcode });
  const { ref } = useZxing({
    onDecodeResult: (result) => handleDecode(result.getText()),
  });

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualBarcode.trim()) return;
    processBarcode(manualBarcode.trim());
    setManualBarcode("");
  };

  return (
    <Paper sx={{ p: 2, m: 2 }}>
      <Typography variant="h4" gutterBottom>
        Barcode Scanner
      </Typography>

      <FormControl component="fieldset" sx={{ mb: 2 }}>
        <FormLabel>Modus</FormLabel>
        <RadioGroup row value={mode} onChange={(e) => setMode(e.target.value as "add" | "remove")}>
          <FormControlLabel value="add" control={<Radio />} label="Hinzufügen" />
          <FormControlLabel value="remove" control={<Radio />} label="Entfernen" />
        </RadioGroup>
      </FormControl>

      <video ref={ref} style={{ width: "100%", maxHeight: 300, borderRadius: 8 }} />

      {lastScanned && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Letzter Scan: {lastScanned}
        </Typography>
      )}

      <form onSubmit={handleManualSubmit}>
        <TextField
          label="Barcode manuell eingeben"
          variant="outlined"
          fullWidth
          margin="normal"
          value={manualBarcode}
          onChange={(e) => setManualBarcode(e.target.value)}
        />

        {mode === "add" && (
          <>
            <Select
              value={selectedLocation}
              onChange={(e) => setSelectedLocation(e.target.value)}
              displayEmpty
              fullWidth
              sx={{ mb: 2 }}
            >
              <MenuItem value="">Lagerort auswählen...</MenuItem>
              {locations.map((loc) => (
                <MenuItem key={loc.id} value={loc.name}>
                  {loc.name}
                </MenuItem>
              ))}
            </Select>

            <TextField
              label="Neuer Lagerplatz (optional)"
              variant="outlined"
              fullWidth
              margin="normal"
              value={newLocation}
              onChange={(e) => setNewLocation(e.target.value)}
            />

            <TextField
              label="Ablaufdatum (optional)"
              type="date"
              fullWidth
              margin="normal"
              InputLabelProps={{ shrink: true }}
              value={expirationDate}
              onChange={(e) => setExpirationDate(e.target.value)}
            />
          </>
        )}

        <Button
          type="submit"
          variant="contained"
          color={mode === "add" ? "primary" : "secondary"}
          fullWidth
          sx={{ mt: 1 }}
        >
          {mode === "add" ? "Hinzufügen" : "Entfernen"}
        </Button>
      </form>
    </Paper>
  );
};

export default ScanPage;
```

- [ ] **Step 3: Update `App.tsx`** — replace `/scan` placeholder with `ScanPage`

Add import and replace route:
```tsx
import ScanPage from "./pages/ScanPage";
// ...
<Route path="/scan" element={<ScanPage />} />
```

- [ ] **Step 4: Verify build**

```bash
cd recipe-assistant/frontend
npx tsc --noEmit && npm run build
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/
git commit -m "feat: add useScanner hook and ScanPage with camera + manual input"
```

---

## Task 17: ScanStationPage

**Files:**
- Create: `recipe-assistant/frontend/src/pages/ScanStationPage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`

- [ ] **Step 1: Create `ScanStationPage.tsx`**

```tsx
import { useState } from "react";
import { Box, Button, Paper, Typography } from "@mui/material";
import { useZxing } from "react-zxing";
import { useNavigate } from "react-router-dom";
import { useScanner } from "../hooks/useScanner";
import { addItemByBarcode, removeItemByBarcode } from "../api/client";

type Mode = "add" | "remove";

interface FeedbackState {
  message: string;
  type: "success" | "error";
}

const ScanStationPage = () => {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("remove");
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);

  const processBarcode = async (barcode: string) => {
    try {
      const result =
        mode === "add"
          ? await addItemByBarcode(barcode)
          : await removeItemByBarcode(barcode);
      setFeedback({ message: result.message, type: "success" });
    } catch (e) {
      setFeedback({
        message: e instanceof Error ? e.message : "Fehler",
        type: "error",
      });
    }
  };

  const { handleDecode } = useScanner({ onScan: processBarcode, cooldownMs: 2000 });
  const { ref } = useZxing({
    onDecodeResult: (result) => handleDecode(result.getText()),
  });

  return (
    <Box
      sx={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        bgcolor: "#121212",
        color: "white",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 2,
          py: 1,
          bgcolor: "#1e1e1e",
        }}
      >
        <Button
          variant="text"
          sx={{ color: "white", fontSize: "1.2rem" }}
          onClick={() => navigate("/")}
        >
          &larr; Menü
        </Button>
        <Typography variant="h5" fontWeight="bold">
          Scan-Station
        </Typography>
        <Box sx={{ width: 80 }} />
      </Box>

      {/* Camera */}
      <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", p: 2 }}>
        <video
          ref={ref}
          style={{
            width: "100%",
            maxHeight: "100%",
            borderRadius: 12,
            objectFit: "cover",
          }}
        />
      </Box>

      {/* Mode Toggle */}
      <Box sx={{ display: "flex", gap: 1, px: 2, pb: 1 }}>
        <Button
          fullWidth
          variant={mode === "add" ? "contained" : "outlined"}
          onClick={() => setMode("add")}
          sx={{
            py: 2,
            fontSize: "1.3rem",
            fontWeight: "bold",
            bgcolor: mode === "add" ? "#2e7d32" : "transparent",
            borderColor: "#2e7d32",
            color: mode === "add" ? "white" : "#2e7d32",
            "&:hover": { bgcolor: mode === "add" ? "#1b5e20" : "rgba(46,125,50,0.1)" },
          }}
        >
          EINTRAGEN
        </Button>
        <Button
          fullWidth
          variant={mode === "remove" ? "contained" : "outlined"}
          onClick={() => setMode("remove")}
          sx={{
            py: 2,
            fontSize: "1.3rem",
            fontWeight: "bold",
            bgcolor: mode === "remove" ? "#d32f2f" : "transparent",
            borderColor: "#d32f2f",
            color: mode === "remove" ? "white" : "#d32f2f",
            "&:hover": { bgcolor: mode === "remove" ? "#b71c1c" : "rgba(211,47,47,0.1)" },
          }}
        >
          AUSTRAGEN
        </Button>
      </Box>

      {/* Feedback */}
      <Paper
        sx={{
          m: 2,
          mt: 0,
          p: 2,
          textAlign: "center",
          bgcolor: feedback
            ? feedback.type === "success"
              ? "#1b5e20"
              : "#b71c1c"
            : "#333",
          color: "white",
          minHeight: 60,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: 2,
        }}
      >
        <Typography variant="h6" fontWeight="bold">
          {feedback?.message ?? "Bereit zum Scannen..."}
        </Typography>
      </Paper>
    </Box>
  );
};

export default ScanStationPage;
```

- [ ] **Step 2: Update `App.tsx`** — replace `/scan-station` placeholder

Add import and replace route:
```tsx
import ScanStationPage from "./pages/ScanStationPage";
// ...
<Route path="/scan-station" element={<ScanStationPage />} />
```

Note: ScanStationPage renders fullscreen without Navbar. Handle this by conditionally hiding Navbar for the `/scan-station` route in `App.tsx`:

```tsx
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { NotificationProvider } from "./components/NotificationProvider";
import Navbar from "./components/Navbar";
import InventoryPage from "./pages/InventoryPage";
import ScanPage from "./pages/ScanPage";
import ScanStationPage from "./pages/ScanStationPage";

const Placeholder = ({ name }: { name: string }) => (
  <div style={{ padding: 24 }}>{name} - Coming Soon</div>
);

const AppContent = () => {
  const location = useLocation();
  const hideNavbar = location.pathname === "/scan-station";

  return (
    <>
      {!hideNavbar && <Navbar />}
      <Routes>
        <Route path="/" element={<InventoryPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="/scan-station" element={<ScanStationPage />} />
        <Route path="/recipes" element={<Placeholder name="Rezepte" />} />
        <Route path="/chat" element={<Placeholder name="Chat" />} />
      </Routes>
    </>
  );
};

const App = () => (
  <BrowserRouter>
    <NotificationProvider>
      <AppContent />
    </NotificationProvider>
  </BrowserRouter>
);

export default App;
```

- [ ] **Step 3: Verify build**

```bash
cd recipe-assistant/frontend
npx tsc --noEmit && npm run build
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/
git commit -m "feat: add ScanStationPage with fullscreen camera and mode toggle"
```

---

## Task 18: useChat Hook + ChatPage

**Files:**
- Create: `recipe-assistant/frontend/src/hooks/useChat.ts`
- Create: `recipe-assistant/frontend/src/pages/ChatPage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`

- [ ] **Step 1: Create `useChat.ts`**

```typescript
import { useCallback, useEffect, useState } from "react";
import type { ChatMessage } from "../types";
import { sendChatMessage, clearChat, getChatHistory } from "../api/client";

export function useChat(sessionId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const data = await getChatHistory(sessionId);
      setMessages(data.messages);
    } catch {
      // No history yet, that's fine
    }
  }, [sessionId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const send = async (message: string, useIngredients: boolean) => {
    setLoading(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: message }]);

    try {
      const data = await sendChatMessage(message, sessionId, useIngredients);
      setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler");
      // Remove optimistic user message on error
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  const clear = async () => {
    await clearChat(sessionId);
    setMessages([]);
  };

  return { messages, loading, error, send, clear };
}
```

- [ ] **Step 2: Create `ChatPage.tsx`**

```tsx
import { useMemo, useState } from "react";
import {
  Box,
  Button,
  CircularProgress,
  Container,
  FormControlLabel,
  Paper,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChat } from "../hooks/useChat";

const ChatPage = () => {
  const sessionId = useMemo(() => crypto.randomUUID(), []);
  const { messages, loading, error, send, clear } = useChat(sessionId);
  const [input, setInput] = useState("");
  const [useIngredients, setUseIngredients] = useState(false);

  const handleSend = () => {
    if (!input.trim() || loading) return;
    send(input.trim(), useIngredients);
    setInput("");
  };

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        KI-Chat Assistent
      </Typography>

      <FormControlLabel
        control={
          <Switch
            checked={useIngredients}
            onChange={() => setUseIngredients(!useIngredients)}
          />
        }
        label="Zutaten aus dem Inventar nutzen"
        sx={{ mb: 2 }}
      />

      <Paper
        elevation={3}
        sx={{
          p: 2,
          maxHeight: "60vh",
          overflowY: "auto",
          mb: 2,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {messages.length === 0 ? (
          <Typography variant="body1" color="text.secondary">
            Starte eine Unterhaltung mit der KI!
          </Typography>
        ) : (
          messages.map((msg, i) => (
            <Paper
              key={i}
              sx={{
                p: 1,
                mb: 1,
                bgcolor: msg.role === "user" ? "#e3f2fd" : "#f1f8e9",
                alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "80%",
              }}
            >
              <Typography variant="caption" color="text.secondary">
                {msg.role === "user" ? "Du" : "Assistent"}
              </Typography>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content}
              </ReactMarkdown>
            </Paper>
          ))
        )}
      </Paper>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      <TextField
        fullWidth
        label="Nachricht eingeben..."
        variant="outlined"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        disabled={loading}
        sx={{ mb: 2 }}
      />

      <Box sx={{ display: "flex", gap: 2 }}>
        <Button
          variant="contained"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          {loading ? <CircularProgress size={24} /> : "Senden"}
        </Button>
        <Button variant="outlined" color="secondary" onClick={clear}>
          Chat zurücksetzen
        </Button>
      </Box>
    </Container>
  );
};

export default ChatPage;
```

- [ ] **Step 3: Update `App.tsx`** — replace `/chat` placeholder

Add import and replace route:
```tsx
import ChatPage from "./pages/ChatPage";
// ...
<Route path="/chat" element={<ChatPage />} />
```

- [ ] **Step 4: Verify build**

```bash
cd recipe-assistant/frontend
npx tsc --noEmit && npm run build
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/
git commit -m "feat: add useChat hook and ChatPage with Claude integration"
```

---

## Task 19: RecipesPage

**Files:**
- Create: `recipe-assistant/frontend/src/pages/RecipesPage.tsx`
- Modify: `recipe-assistant/frontend/src/App.tsx`

- [ ] **Step 1: Create `RecipesPage.tsx`**

```tsx
import { useState } from "react";
import {
  Alert,
  Button,
  CircularProgress,
  Container,
  FormControlLabel,
  Grid,
  Paper,
  Switch,
  Typography,
} from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getRecipeSuggestions, generateRecipeImage } from "../api/client";
import type { Recipe } from "../types";

const RecipesPage = () => {
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recipeImage, setRecipeImage] = useState("");
  const [generateImages, setGenerateImages] = useState(false);

  const fetchRecipes = async () => {
    setLoading(true);
    setError("");
    setSelectedRecipe(null);

    try {
      const data = await getRecipeSuggestions();
      setRecipes(data.recipes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler beim Abrufen der Rezepte.");
    } finally {
      setLoading(false);
    }
  };

  const handleRecipeClick = async (recipe: Recipe) => {
    setSelectedRecipe(recipe);
    setRecipeImage("");

    if (generateImages) {
      setLoading(true);
      try {
        const data = await generateRecipeImage(recipe.name);
        if (data.image_url) setRecipeImage(data.image_url);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Fehler bei Bildgenerierung.");
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <Container sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom>
        KI-Kochassistent
      </Typography>

      <FormControlLabel
        control={
          <Switch
            checked={generateImages}
            onChange={() => setGenerateImages(!generateImages)}
          />
        }
        label="Bilder für Rezepte generieren (DALL-E)"
        sx={{ mb: 2 }}
      />

      {recipes.length === 0 && (
        <Button
          variant="contained"
          onClick={fetchRecipes}
          disabled={loading}
          sx={{ mb: 2 }}
        >
          {loading ? <CircularProgress size={24} /> : "Rezeptvorschläge abrufen"}
        </Button>
      )}

      {error && (
        <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
          {error}
        </Alert>
      )}

      {!selectedRecipe && recipes.length > 0 && (
        <Grid container spacing={2} sx={{ mt: 2 }}>
          {recipes.map((recipe, i) => (
            <Grid key={i} size={{ xs: 12, sm: 6 }}>
              <Button
                variant="contained"
                fullWidth
                onClick={() => handleRecipeClick(recipe)}
              >
                {recipe.name}
              </Button>
            </Grid>
          ))}
        </Grid>
      )}

      {selectedRecipe && (
        <Paper elevation={3} sx={{ mt: 2, p: 2, maxHeight: "60vh", overflowY: "auto" }}>
          <Typography variant="h5" gutterBottom>
            {selectedRecipe.name}
          </Typography>
          <Typography variant="subtitle1" color="text.secondary" gutterBottom>
            {selectedRecipe.short_description}
          </Typography>

          {recipeImage && (
            <img
              src={recipeImage}
              alt={selectedRecipe.name}
              style={{ width: "100%", borderRadius: 10, marginBottom: 10 }}
            />
          )}

          <Typography variant="h6">Zutaten:</Typography>
          <ul>
            {selectedRecipe.ingredients.map((ing, i) => (
              <li key={i}>{ing}</li>
            ))}
          </ul>

          <Typography variant="h6">Anleitung:</Typography>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {selectedRecipe.instructions}
          </ReactMarkdown>

          <Button
            variant="outlined"
            color="secondary"
            onClick={() => setSelectedRecipe(null)}
            sx={{ mt: 2 }}
          >
            Zurück zur Auswahl
          </Button>
        </Paper>
      )}
    </Container>
  );
};

export default RecipesPage;
```

- [ ] **Step 2: Update `App.tsx`** — replace `/recipes` placeholder

Add import and replace route:
```tsx
import RecipesPage from "./pages/RecipesPage";
// ...
<Route path="/recipes" element={<RecipesPage />} />
```

- [ ] **Step 3: Verify build**

```bash
cd recipe-assistant/frontend
npx tsc --noEmit && npm run build
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/
git commit -m "feat: add RecipesPage with Claude suggestions and DALL-E images"
```

---

## Task 20: FastAPI Static Serving + SPA Fallback

**Files:**
- Modify: `recipe-assistant/backend/app/main.py`

- [ ] **Step 1: Update `main.py` with static file serving and SPA fallback**

```python
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import inventory, storage, assistant

app = FastAPI(title="Recipe Assistant API", version="2.0.0")

app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(storage.router, prefix="/api/storage-locations", tags=["storage"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])

# Serve frontend static files in production
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "build"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        """Serve index.html for all non-API routes (SPA routing)."""
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
```

- [ ] **Step 2: Verify API still works**

```bash
cd recipe-assistant/backend
pytest -v
```

Expected: All tests pass. (Static serving only activates when `build/` exists.)

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/app/main.py
git commit -m "feat: add static file serving and SPA fallback to FastAPI"
```

---

## Task 21: Docker + Supervisor + HA Config

**Files:**
- Create: `recipe-assistant/Dockerfile`
- Create: `recipe-assistant/run.sh`
- Create: `recipe-assistant/supervisord.conf`
- Modify: `recipe-assistant/config.json`
- Modify: `repository.json` (project root)

- [ ] **Step 1: Create `supervisord.conf`**

```ini
[supervisord]
nodaemon=true
logfile=/dev/stdout
logfile_maxbytes=0
loglevel=info

[program:postgres]
command=/usr/lib/postgresql/16/bin/postgres -D /data/postgres -c listen_addresses=localhost
user=postgres
autostart=true
autorestart=true
priority=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:uvicorn]
command=/usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
directory=/app/backend
autostart=true
autorestart=true
priority=30
startsecs=5
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

- [ ] **Step 2: Create `run.sh`**

```bash
#!/bin/bash
set -e

# Initialize Postgres data directory if needed
if [ ! -d "/data/postgres" ]; then
    mkdir -p /data/postgres
    chown postgres:postgres /data/postgres
    su - postgres -c "/usr/lib/postgresql/16/bin/initdb -D /data/postgres"
fi

# Ensure postgres owns the data dir
chown -R postgres:postgres /data/postgres

# Start Postgres temporarily to run migrations
su - postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /data/postgres -l /tmp/pg_init.log start"

# Wait for Postgres to be ready
until su - postgres -c "pg_isready -q"; do
    sleep 1
done

# Create database and user if they don't exist
su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = 'recipe'\" | grep -q 1 || psql -c \"CREATE DATABASE recipe\""
su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname = 'recipe'\" | grep -q 1 || psql -c \"CREATE USER recipe WITH PASSWORD 'recipe'\""
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE recipe TO recipe\""
su - postgres -c "psql -d recipe -c \"GRANT ALL ON SCHEMA public TO recipe\""

# Run Alembic migrations
cd /app/backend
alembic upgrade head

# Stop temporary Postgres (Supervisor will restart it)
su - postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /data/postgres stop"

# Start Supervisor (manages Postgres + uvicorn)
exec supervisord -c /app/supervisord.conf
```

- [ ] **Step 3: Create `Dockerfile`**

```dockerfile
# Stage 1: Build Frontend
FROM node:22-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Production
FROM python:3.12-slim

# Install PostgreSQL 16 + Supervisor
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gnupg2 lsb-release curl ca-certificates && \
    echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-16 \
        supervisor && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/pyproject.toml ./backend/
RUN pip install --no-cache-dir ./backend

# Copy backend
COPY backend/ ./backend/

# Copy frontend build
COPY --from=frontend-build /frontend/build ./frontend/build

# Copy container config
COPY supervisord.conf run.sh ./
RUN chmod +x run.sh

# Create data directory
RUN mkdir -p /data/postgres && chown postgres:postgres /data/postgres

EXPOSE 8080

ENTRYPOINT ["./run.sh"]
```

- [ ] **Step 4: Update `config.json`**

```json
{
  "name": "Recipe Assistant",
  "version": "2.0",
  "slug": "recipe_assistant",
  "description": "Rezept- und Chat-Assistent mit Claude AI und Inventarverwaltung",
  "url": "https://github.com/woerty/inv-addon",
  "startup": "application",
  "boot": "auto",
  "arch": ["aarch64", "amd64"],
  "panel_icon": "mdi:food",
  "panel_title": "Recipe Assistant",
  "ingress": true,
  "ingress_port": 8080,
  "map": ["config:rw", "data:rw"],
  "options": {
    "anthropic_api_key": "",
    "openai_api_key": ""
  },
  "schema": {
    "anthropic_api_key": "password",
    "openai_api_key": "password"
  }
}
```

- [ ] **Step 5: Update `repository.json`** (project root)

```json
{
  "name": "Recipe Assistant Repository",
  "url": "https://github.com/woerty/inv-addon",
  "maintainer": "woerty"
}
```

- [ ] **Step 6: Build Docker image locally to verify**

```bash
cd recipe-assistant
docker build -t recipe-assistant:2.0 .
```

Expected: Build completes successfully.

- [ ] **Step 7: Commit**

```bash
git add recipe-assistant/Dockerfile recipe-assistant/run.sh recipe-assistant/supervisord.conf recipe-assistant/config.json repository.json
git commit -m "feat: add Docker + Supervisor + HA config for containerized deployment"
```

---

## Task 22: Cleanup Old Code

**Files:**
- Delete: `recipe-assistant/app/` (old Flask backend)
- Delete: `recipe-assistant/frontend/src/components/addItem.js`
- Delete: `recipe-assistant/frontend/src/components/deleteItem.js`
- Delete: `recipe-assistant/frontend/src/components/InventoryManager_o.js`

- [ ] **Step 1: Remove old backend**

```bash
rm -rf recipe-assistant/app/
```

- [ ] **Step 2: Remove unused legacy frontend files** (if any remain after Task 12 step 1)

```bash
rm -f recipe-assistant/frontend/src/components/addItem.js
rm -f recipe-assistant/frontend/src/components/deleteItem.js
rm -f recipe-assistant/frontend/src/components/InventoryManager_o.js
```

- [ ] **Step 3: Verify nothing references old code**

```bash
cd recipe-assistant
grep -r "localhost:5000" --include="*.ts" --include="*.tsx" --include="*.py" || echo "No hardcoded localhost:5000 references"
grep -r "openai_client" --include="*.py" || echo "No old openai_client references"
```

Expected: No matches found.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove old Flask backend and unused legacy files"
```

---

## Task 23: End-to-End Verification

- [ ] **Step 1: Run full backend test suite**

```bash
cd recipe-assistant/backend
pytest -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 2: Build frontend**

```bash
cd recipe-assistant/frontend
npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Docker build**

```bash
cd recipe-assistant
docker build -t recipe-assistant:2.0 .
```

Expected: Build completes.

- [ ] **Step 4: Start and smoke test**

```bash
docker run -d --name ra-test -p 8080:8080 -e ANTHROPIC_API_KEY=test -e OPENAI_API_KEY=test recipe-assistant:2.0
sleep 10
curl -s http://localhost:8080/api/inventory/ | python3 -m json.tool
curl -s http://localhost:8080/ | head -5
docker stop ra-test && docker rm ra-test
```

Expected: API returns `[]`, HTML returns the React app's `index.html`.

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: end-to-end verification fixes"
```
