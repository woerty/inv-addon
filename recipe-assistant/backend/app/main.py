import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import inventory, storage, assistant, persons, picnic, tracked_products, dashboard
from app.services.picnic.client import PicnicAPIError
from app.services.restock_schedule import reconcile_forever


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In dev mode with SQLite: auto-create tables
    if "sqlite" in get_settings().database_url:
        from app.models import (  # noqa: F401
            InventoryItem,
            StorageLocation,
            ChatMessage,
            InventoryLog,
            Person,
            PicnicProduct,
            PicnicDeliveryImport,
            PicnicEanLink,
            TrackedProduct,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    settings = get_settings()
    restock_task = None
    if settings.picnic_email and settings.picnic_password:
        restock_task = asyncio.create_task(reconcile_forever())
    yield
    if restock_task is not None:
        restock_task.cancel()
        with suppress(asyncio.CancelledError):
            await restock_task


app = FastAPI(title="Recipe Assistant API", version="2.0.0", lifespan=lifespan)


@app.exception_handler(PicnicAPIError)
async def picnic_api_error(_: Request, exc: PicnicAPIError) -> JSONResponse:
    # Surfaced via "error" so the frontend's request() shows the text as-is.
    return JSONResponse(
        status_code=502,
        content={"detail": {"error": f"Picnic hat die Anfrage abgelehnt: {exc.message or exc.code}"}},
    )


app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(storage.router, prefix="/api/storage-locations", tags=["storage"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])
app.include_router(persons.router, prefix="/api/persons", tags=["persons"])
app.include_router(picnic.router, prefix="/api/picnic", tags=["picnic"])
app.include_router(
    tracked_products.router,
    prefix="/api/tracked-products",
    tags=["tracked-products"],
)
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])

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
