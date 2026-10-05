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

#### Local Picnic auth (dev)

To exercise real Picnic endpoints locally (no token-copying from the HA host):

```bash
cp .env.example .env          # then fill PICNIC_MAIL / PICNIC_PASSWORD
python -m app.services.picnic.setup   # interactive 2FA, writes the token
python -m uvicorn app.main:app --reload
```

The token path comes from `PICNIC_TOKEN_PATH` (Settings/.env). It defaults to
`/data/picnic_token.json` (the HA addon's persistent dir) and is overridden to a
local file in dev. Both the setup CLI and the runtime client read this same
setting, so a single `.env` configures everything.

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
- **Pages** (`pages/`): Route-based pages. Key: `InventoryPage` (start page at `/`), `DashboardPage` (`/dashboard`), `ScanPage`, `PicnicStorePage` (store, cart, orders, restock rules under "Abos"). `ScanStationPage` (iPad kiosk) is disabled: no route, no nav entry
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
- Picnic integration uses `python-picnic-api2` 2.x. It returns pydantic models; `app/services/picnic/client.py` unwraps them to the raw API dicts (`.raw`) that the rest of the code parses, and raises `PicnicAPIError` on Picnic error payloads (the library passes those through as normal responses). Check a new major version against live data before raising the cap
- Auto-restock (`app/services/restock.py`) matches rules to inventory through the Picnic product, not a single barcode: `picnic_ean_links` maps every scanned EAN to its picnic_id (`app/services/picnic/ean_links.py`). Besides the per-decrement check, `reconcile_all` re-checks every rule 60 s after startup, every 4 h, and via `POST /api/tracked-products/reconcile`. Only the reconcile writes links and asks Picnic live (throttled, stops at the first failed lookup; a burst of a few hundred got the Picnic account briefly blocked); decrements and imports use stored links only. Deliveries completed within 24 h and not imported still count as incoming, because deliveries are scanned in rather than imported
- ass3 link (`app/services/ass3_link.py`, on only with the `ass3_url` + `ass3_token` options): the add-on long-polls ass3 for commands and pushes snapshots (inventory, rules with their linked stock, 48 h of `inventory_log` as history, Picnic cart/open orders); ass3 never calls in. Only `scan_out`, `cart_add`, `cart_remove`, `picnic_search`, `refresh` run -- no checkout. `scan_out` goes through `app/services/inventory_ops.scan_out_one`, the same path as the scanner endpoint. Picnic is asked live only every 30 min, after cart commands/refresh (at most once a minute), and Picnic commands are capped at 40 per 10 min
- `inventory_log` entries carry the item's `name` and `quantity_before`/`quantity_after` (pass them to `inventory_ops.log_action`); `inventory_log.timestamp` is naive local time of the Postgres server's TimeZone (UTC on SQLite), see `ass3_link.build_history`
- Frontend npm install requires `--legacy-peer-deps` flag (see Dockerfile)
- Product matching uses `rapidfuzz` for fuzzy string matching
