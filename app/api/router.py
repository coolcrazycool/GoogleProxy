from __future__ import annotations

from fastapi import APIRouter

from app.api import auth, drive, sheets

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(drive.router)
api_router.include_router(sheets.router)
