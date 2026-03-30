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
