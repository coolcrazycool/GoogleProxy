from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_internal_token, get_token_manager
from app.auth.token_manager import TokenManager
from app.models.schemas import (
    GoogleTokenResponse,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=200)
def register(
    body: RegisterRequest,
    token_manager: TokenManager = Depends(get_token_manager),
) -> RegisterResponse:
    """
    Register a Google service account JSON (base64-encoded).

    Returns a stable **internal_token** (UUID) that never changes for the same
    account.  Pass it as `Authorization: Bearer <internal_token>` on all
    subsequent requests.
    """
    try:
        account_json = json.loads(base64.b64decode(body.account_json_b64))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 or JSON in account_json_b64")
    internal_token = token_manager.register(account_json)
    return RegisterResponse(
        internal_token=internal_token,
        message="Registered successfully",
    )


@router.get("/google-token", response_model=GoogleTokenResponse)
def get_google_token(
    internal_token: str = Depends(get_internal_token),
    token_manager: TokenManager = Depends(get_token_manager),
) -> GoogleTokenResponse:
    """
    Return the current (possibly refreshed) Google access token for the caller.

    The token is fetched from cache if still valid; otherwise it is refreshed
    transparently.
    """
    info = token_manager.get_token_info(internal_token)
    return GoogleTokenResponse(
        access_token=info["access_token"],
        expires_at=info["expires_at"] or "",
    )
