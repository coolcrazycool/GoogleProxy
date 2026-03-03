from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.router import api_router
from app.auth.token_manager import TokenManager
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the data directory exists
    Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    # Initialise the shared TokenManager (reads/creates the storage file)
    app.state.token_manager = TokenManager(settings.tokens_file_path)
    yield
    # No explicit cleanup needed


app = FastAPI(
    title="Google API Proxy",
    description=(
        "Proxy server for Google Sheets and Drive API. "
        "Register your service account JSON to receive a stable internal token, "
        "then use it on all subsequent requests."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
