# Recipe Assistant Rewrite - Design Spec

## Overview

Complete rewrite of the Recipe Assistant Home Assistant Add-on. Migrates from Flask + JavaScript + SQLite + OpenAI to FastAPI + TypeScript + PostgreSQL + Claude (with DALL-E for images only). Adds camera-based barcode scanning, a dedicated scan station mode, and proper HA Ingress compatibility.

## Goals

- Fix all existing bugs (undefined `openai_client`, missing DELETE endpoint, broken CORS, hardcoded URLs)
- Migrate AI from OpenAI to Claude (Anthropic SDK) for chat and recipes; keep OpenAI only for DALL-E image generation
- Modernize stack: FastAPI, TypeScript, Vite, PostgreSQL + SQLAlchemy + Alembic
- Add camera-based barcode scanning for iPad use at trash/recycling station
- Make HA Ingress compatible while supporting local development
- Proper API key management via HA config UI

## Architecture

### Container Layout

Single Docker container managed by Supervisor running three processes:

1. **PostgreSQL 16** - starts first, data on `/data/postgres` (HA persistent volume)
2. **Alembic** - runs migrations once on startup (after Postgres ready)
3. **FastAPI** (uvicorn) - port 8080, serves API + static frontend build

Single port (8080) exposed via HA Ingress. No separate frontend server. FastAPI mounts the Vite build as static files and serves `index.html` for all non-`/api/*` routes (SPA routing).

### Project Structure

```
recipe-assistant/
├── config.json                     # HA Add-on Manifest
├── Dockerfile                      # Multi-stage Build
├── run.sh                          # Supervisor startup
├── supervisord.conf                # Process Manager Config
│
├── backend/
│   ├── pyproject.toml              # Python Dependencies
│   ├── alembic.ini                 # DB Migration Config
│   ├── alembic/
│   │   └── versions/               # Migration Scripts
│   ├── app/
│   │   ├── main.py                 # FastAPI App + Startup
│   │   ├── config.py               # Settings (HA options.json + .env fallback)
│   │   ├── database.py             # SQLAlchemy Engine + Session
│   │   ├── models/
│   │   │   ├── inventory.py        # InventoryItem, StorageLocation
│   │   │   ├── chat.py             # ChatMessage
│   │   │   └── log.py              # InventoryLog
│   │   ├── schemas/
│   │   │   ├── inventory.py        # Pydantic Request/Response Models
│   │   │   ├── recipe.py           # Recipe Schemas
│   │   │   └── chat.py             # Chat Schemas
│   │   ├── routers/
│   │   │   ├── inventory.py        # /api/inventory/*
│   │   │   ├── assistant.py        # /api/assistant/*
│   │   │   └── storage.py          # /api/storage-locations/*
│   │   └── services/
│   │       ├── barcode.py          # OpenFoodFacts Lookup
│   │       ├── ai_chat.py          # Claude Chat Service
│   │       ├── ai_recipes.py       # Claude Recipe Suggestions
│   │       └── ai_images.py        # OpenAI DALL-E Service
│   └── tests/
│       ├── conftest.py
│       ├── test_inventory.py
│       ├── test_assistant.py
│       └── test_barcode.py
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts              # Vite Config with API proxy
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx                # Entry Point
│       ├── App.tsx                 # Router
│       ├── api/
│       │   └── client.ts           # Central API Client (relative URLs)
│       ├── hooks/
│       │   ├── useInventory.ts     # Inventory State + CRUD
│       │   ├── useScanner.ts       # Camera Barcode Hook
│       │   └── useChat.ts          # Chat State
│       ├── components/
│       │   ├── Navbar.tsx
│       │   ├── NotificationProvider.tsx
│       │   └── common/             # Shared UI Components
│       ├── pages/
│       │   ├── InventoryPage.tsx   # Inventory table with inline editing
│       │   ├── ScanPage.tsx        # Full scan page (add/remove + camera)
│       │   ├── ScanStationPage.tsx # Dedicated scan station for iPad
│       │   ├── RecipesPage.tsx     # Claude recipe suggestions + DALL-E images
│       │   └── ChatPage.tsx        # Claude chat assistant
│       └── types/
│           └── index.ts            # Shared TypeScript Types
│
└── repository.json
```

## Database

### PostgreSQL + SQLAlchemy + Alembic

PostgreSQL 16 running inside the container. Data persisted to `/data/postgres` (HA persistent volume, requires `data:rw` map). SQLAlchemy async engine (`asyncpg` driver) with Alembic for schema migrations. All DB access is async via `AsyncSession`.

### Models

**InventoryItem**
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PK, autoincrement |
| barcode | String | unique, indexed |
| name | String | |
| quantity | Integer | default 1 |
| category | String | default "Unbekannt" |
| storage_location_id | Integer | FK → StorageLocation, nullable |
| expiration_date | Date | nullable, optional manual input |
| added_date | DateTime | auto (server default) |
| updated_date | DateTime | auto-update on change |

**StorageLocation**
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PK, autoincrement |
| name | String | unique |

**InventoryLog**
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PK, autoincrement |
| barcode | String | |
| action | String | "add", "remove", "update", "delete" |
| details | String | nullable, e.g. "quantity: 3 → 2" |
| timestamp | DateTime | auto |

**ChatMessage**
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PK, autoincrement |
| session_id | String | indexed, UUID per conversation |
| role | String | "user", "assistant", "system" |
| content | String | |
| timestamp | DateTime | auto |

### Key changes from current schema

- `storage_location` becomes a proper FK relation instead of free-text
- `expiration_date` is nullable instead of hardcoded `1900-01-01`
- Chat gets `session_id` for multiple conversations
- Log gets `details` field for meaningful history
- `updated_date` tracks last modification

## API Endpoints

All endpoints under `/api/` prefix.

### Inventory (`/api/inventory`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | List all items. Query params: `?search=`, `?sort_by=`, `?order=` |
| POST | `/barcode` | Add item by barcode (OpenFoodFacts lookup, +1 if exists) |
| POST | `/remove` | Remove 1 from item by barcode (delete if quantity reaches 0) |
| PUT | `/{barcode}` | Update item (quantity, storage_location, expiration_date) |
| DELETE | `/{barcode}` | Delete item completely |

### Storage Locations (`/api/storage-locations`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | List all locations |
| POST | `/` | Create new location |
| DELETE | `/{id}` | Delete location |

### Assistant (`/api/assistant`)

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/recipes` | Recipe suggestions based on inventory (Claude) |
| POST | `/recipe-image` | Generate image for recipe (DALL-E) |
| POST | `/chat` | Send chat message (Claude) |
| POST | `/chat/clear/{session_id}` | Clear chat session by session_id |
| GET | `/chat/history/{session_id}` | Get chat history for session |

All endpoints hitting external APIs are async.

## Services

### Barcode Service (`services/barcode.py`)

- Async `httpx` call to OpenFoodFacts API
- Timeout: 5 seconds
- Fallback on 404: create item anyway with "Unbekanntes Produkt" + barcode as name

### Claude Chat Service (`services/ai_chat.py`)

- Anthropic Python SDK
- Model: `claude-sonnet-4-6`
- System prompt: German cooking assistant
- Loads chat history from DB, sends to Claude
- Optional: inventory ingredients as context on first message of session
- Max tokens: 4096

### Claude Recipe Service (`services/ai_recipes.py`)

- Model: `claude-sonnet-4-6`
- Queries inventory items, formats as ingredient list
- Structured output via Claude Tool Use: response validated against `Recipe` Pydantic schema
- No fragile JSON parsing - schema is enforced by the API

### DALL-E Image Service (`services/ai_images.py`)

- OpenAI SDK, image generation only
- Model: `dall-e-3`, 1024x1024
- Async call
- Separate API key from Claude

## Configuration

### `config.py` - Pydantic BaseSettings

```python
class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://recipe:recipe@localhost:5432/recipe"
    anthropic_api_key: str
    openai_api_key: str
    environment: str = "production"  # "development" | "production"
```

### Two config sources

- **Production (HA):** Reads from `/data/options.json` (HA Add-on config UI)
- **Development:** Reads from `.env` file

`config.json` schema exposes `anthropic_api_key` and `openai_api_key` as password fields in HA UI.

## Frontend

### Tech Stack

- React 19 + TypeScript + Vite
- MUI (Material UI)
- react-router-dom for routing
- react-zxing for camera barcode scanning
- react-markdown + remark-gfm for chat rendering

### API Client (`api/client.ts`)

Single source of truth for all API calls. Uses relative URLs (`/api/inventory`). In dev, Vite proxies `/api/*` to `localhost:8000` (FastAPI). In prod, same origin - no CORS needed.

### Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | InventoryPage | Table with search, sort, inline edit for quantity/location/expiry, delete button |
| `/scan` | ScanPage | Camera scanner + manual text field, add/remove toggle, location picker, optional expiry date |
| `/scan-station` | ScanStationPage | Dedicated iPad scan station (see below) |
| `/recipes` | RecipesPage | Claude recipe suggestions, optional DALL-E images |
| `/chat` | ChatPage | Claude chat assistant, inventory context toggle |

### ScanStationPage Design

```
┌─────────────────────────────┐
│  [← Menu]    Scan-Station   │  ← Slim header bar
├─────────────────────────────┤
│                             │
│     ┌─────────────────┐     │
│     │                 │     │
│     │   Camera Feed   │     │  ← Large camera view, ~60% height
│     │                 │     │
│     └─────────────────┘     │
│                             │
│  ┌───────────┬────────────┐ │
│  │ EINTRAGEN │ AUSTRAGEN  │ │  ← Large toggle buttons, color-coded
│  │  (green)  │  (red)     │ │     Green = Add, Red = Remove
│  └───────────┴────────────┘ │
│                             │
│  ┌─────────────────────────┐│
│  │ "Milch entfernt (2 rem)"││  ← Feedback area: last scan result
│  └─────────────────────────┘│
└─────────────────────────────┘
```

- Minimal header with back button
- Camera takes up most of the screen
- Large, clear mode toggle: Eintragen (green) / Austragen (red)
- Feedback area at bottom showing last scan result
- 2s cooldown between scans of the same barcode
- Touch-optimized, large fonts, iPad-friendly

### Hooks

- `useInventory()` - fetch, add, remove, update, delete + state management
- `useScanner(onScan: (barcode: string) => void)` - camera stream, barcode detection, cooldown logic
- `useChat(sessionId)` - messages, send, clear, history

### State Management

React Hooks + Context. No Redux/Zustand needed for this scope. `NotificationProvider` as Context for app-wide snackbar notifications.

## Deployment

### Dockerfile (Multi-stage)

```
Stage 1: frontend-build
  → Node 22, npm install, vite build

Stage 2: production
  → Python 3.12
  → PostgreSQL 16 (via apt)
  → Copy backend + frontend build
  → pip install dependencies
  → Supervisor as entrypoint
```

### Supervisor Processes

1. **PostgreSQL** - starts first, data on `/data/postgres`
2. **Alembic** - runs migrations once on startup (after Postgres ready check)
3. **uvicorn** - FastAPI on port 8080

### HA Add-on Config (`config.json`)

```json
{
  "name": "Recipe Assistant",
  "version": "2.0",
  "slug": "recipe_assistant",
  "description": "Rezept- und Chat-Assistent mit Claude AI",
  "startup": "application",
  "boot": "auto",
  "arch": ["aarch64", "amd64"],  // dropped armv7/i386 - not viable with Postgres 16 + Python 3.12
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

### Local Development

- **Backend:** `uvicorn app.main:app --reload` + local Postgres (or Docker)
- **Frontend:** `npm run dev` with Vite proxy to `:8000`
- **Config:** `.env` file for API keys

## Testing

### Backend (pytest + httpx)

- **Unit Tests:** Services tested in isolation (barcode lookup with mocked httpx, AI services with mocked API responses)
- **Integration Tests:** API endpoints against real test database

| Area | Tests |
|------|-------|
| Inventory CRUD | Add, remove, update, delete, duplicate barcode, quantity→0 triggers delete |
| Barcode Service | OpenFoodFacts success, 404 fallback, timeout handling |
| Storage Locations | Create, duplicate prevention, delete, FK constraint |
| AI Services | Claude/OpenAI calls mocked, schema validation of responses |
| Config | HA options.json parsing, .env fallback |

### Frontend

No frontend tests initially. Business logic lives in the backend. Can be added later once the app is stable.
