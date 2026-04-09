# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Recipe Assistant is a Home Assistant add-on for household inventory management with AI chat (Claude), barcode scanning, Picnic grocery integration, and auto-restock. Full-stack app: FastAPI backend + React/TypeScript frontend, deployed as a single Docker container with PostgreSQL.

## Commands

### Backend (from `recipe-assistant/backend/`)

```bash
# Install (dev)
pip install -e .[dev]

# Run dev server
python -m uvicorn app.main:app --reload   # port 8000

# Tests
pytest                                     # all tests
pytest tests/test_inventory.py             # single file
pytest tests/test_inventory.py::test_name  # single test
pytest -v                                  # verbose

# Database migrations
alembic upgrade head                       # apply all migrations
alembic revision --autogenerate -m "desc"  # create new migration
```

pytest is configured with `asyncio_mode = "auto"` in pyproject.toml -- no need for `@pytest.mark.asyncio` on tests.

### Frontend (from `recipe-assistant/frontend/`)

```bash
npm install
npm run dev      # dev server on port 3000, proxies /api to localhost:8000
npm run build    # production build to build/
```

### Docker (from `recipe-assistant/`)

```bash
docker build -t recipe-assistant .
```

## Architecture

### Backend (`recipe-assistant/backend/app/`)

- **FastAPI** async-first application. Entry point: `app/main.py`
- **Database**: async SQLAlchemy + AsyncPG (PostgreSQL in prod, SQLite+aiosqlite in dev/test)
- **Routers** (`app/routers/`): REST endpoints under `/api/`. Main routers: `inventory`, `tracked_products`, `picnic`, `assistant`, `storage`, `persons`
- **Models** (`app/models/`): SQLAlchemy ORM models. All share a `Base` from `app/database.py`
- **Schemas** (`app/schemas/`): Pydantic request/response models
- **Services** (`app/services/`): Business logic and external integrations (barcode lookup via OpenFoodFacts, AI chat/recipes, Picnic API client, restock logic)
- **Alembic** (`alembic/`): Database migrations. Config in `alembic.ini`

### Frontend (`recipe-assistant/frontend/src/`)

- **React 19 + TypeScript + Vite** with Material-UI
- **Pages** (`pages/`): Route-based pages. Key: `InventoryPage`, `ScanPage`, `ScanStationPage` (iPad kiosk mode), `TrackedProductsPage`, `ShoppingListPage`
- **Hooks** (`hooks/`): Custom hooks for API state management (`useInventory`, `usePicnic`, `useTrackedProducts`, etc.)
- **API client** (`api/client.ts`): Centralized fetch wrapper for all backend endpoints
- Uses relative base path (`./`) for Home Assistant Ingress compatibility

### Configuration (`app/config.py`)

Two-tier config via `Settings` (pydantic-settings):
- **Production**: Reads `/data/options.json` (HA add-on config), sets `environment="production"`
- **Development**: Reads `.env` file, uses SQLite by default
- `picnic_email` has alias support: accepts `PICNIC_MAIL` or `PICNIC_EMAIL` env vars

### Testing (`backend/tests/`)

- Uses SQLite in-memory DB via `conftest.py` (overrides `get_db` dependency)
- External HTTP calls are mocked (e.g., `lookup_barcode` patched in autouse fixture)
- `AsyncClient` with `ASGITransport` for endpoint testing
- Tables are created/dropped per test via `setup_db` autouse fixture

### Deployment

Single Docker container running supervisord with PostgreSQL 16 + uvicorn on port 8080. `run.sh` handles DB initialization and Alembic migrations on startup. Frontend is served as static files by FastAPI with SPA fallback routing.

## Key Patterns

- All database access is async (`AsyncSession`, async router handlers)
- Dependency injection via FastAPI `Depends()` for DB sessions and settings
- Picnic integration uses `python-picnic-api2>=1.3.3` (required for 2FA support)
- Frontend npm install requires `--legacy-peer-deps` flag (see Dockerfile)
- Product matching uses `rapidfuzz` for fuzzy string matching
