from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.token_manager import TokenManager

_security = HTTPBearer()


def get_token_manager(request: Request) -> TokenManager:
    """Retrieve the TokenManager singleton from app.state."""
    return request.app.state.token_manager


def get_current_credentials(
    http_creds: HTTPAuthorizationCredentials = Depends(_security),
    token_manager: TokenManager = Depends(get_token_manager),
):
    """
    FastAPI dependency that resolves the Bearer token from the Authorization header
    into live Google credentials, refreshing if necessary.

    Usage in route handlers::

        @router.get("/something")
        def my_endpoint(creds = Depends(get_current_credentials)):
            service = SheetsService(creds)
            ...
    """
    return token_manager.get_google_credentials(http_creds.credentials)


def get_internal_token(
    http_creds: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Return the raw internal token string from the Authorization header."""
    return http_creds.credentials
