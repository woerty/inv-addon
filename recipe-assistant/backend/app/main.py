from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import inventory, storage, assistant


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In dev mode with SQLite: auto-create tables
    if "sqlite" in get_settings().database_url:
        from app.models import InventoryItem, StorageLocation, ChatMessage, InventoryLog  # noqa: F401
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Recipe Assistant API", version="2.0.0", lifespan=lifespan)

app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(storage.router, prefix="/api/storage-locations", tags=["storage"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])

# Serve frontend static files in production
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "build"
if FRONTEND_DIR.exists():

    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        """Serve index.html for all non-API routes (SPA routing)."""
        file_path = (FRONTEND_DIR / full_path).resolve()
        if file_path.is_relative_to(FRONTEND_DIR) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
