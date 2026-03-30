from fastapi import FastAPI

from app.routers import inventory, storage, assistant

app = FastAPI(title="Recipe Assistant API", version="2.0.0")

app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(storage.router, prefix="/api/storage-locations", tags=["storage"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["assistant"])
