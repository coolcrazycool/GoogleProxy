from __future__ import annotations

import base64
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.token_manager import TokenManager
from app.main import app


# ---------------------------------------------------------------------------
# Shared fake data
# ---------------------------------------------------------------------------

FAKE_INTERNAL_TOKEN = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_ACCESS_TOKEN = "ya29.fake-access-token"
FAKE_EXPIRES_AT = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

SAMPLE_ACCOUNT_JSON = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key-id-123",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


# ---------------------------------------------------------------------------
# TokenManager fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_token_file(tmp_path: Path) -> str:
    """Return path to a fresh temporary token storage file."""
    return str(tmp_path / "tokens.json")


@pytest.fixture
def token_manager(tmp_token_file: str) -> TokenManager:
    """Return a real TokenManager backed by a temp file."""
    return TokenManager(tmp_token_file)


def make_mock_credentials(
    token: str = FAKE_ACCESS_TOKEN,
    expires_at: datetime | None = None,
) -> MagicMock:
    """Create a mock Google credentials object."""
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    creds = MagicMock()
    creds.token = token
    creds.expiry = expires_at
    creds.valid = True
    return creds


@pytest.fixture
def mock_credentials() -> MagicMock:
    return make_mock_credentials()


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------

def _make_mock_token_manager() -> MagicMock:
    """Return a MagicMock that behaves like a registered TokenManager."""
    mgr = MagicMock(spec=TokenManager)
    mgr.register.return_value = FAKE_INTERNAL_TOKEN
    mgr.get_google_credentials.return_value = make_mock_credentials()
    mgr.get_token_info.return_value = {
        "access_token": FAKE_ACCESS_TOKEN,
        "expires_at": FAKE_EXPIRES_AT,
    }
    return mgr


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """
    Async HTTP test client with the TokenManager replaced by a mock,
    so no real Google calls are made.
    """
    mock_mgr = _make_mock_token_manager()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        app.state.token_manager = mock_mgr
        yield ac


@pytest_asyncio.fixture
async def client_real_manager(tmp_token_file: str) -> AsyncClient:
    """
    Async HTTP test client that uses a *real* TokenManager backed by a temp file.
    build_credentials is patched so no Google network call is made.
    """
    real_mgr = TokenManager(tmp_token_file)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        app.state.token_manager = real_mgr
        yield ac


# ---------------------------------------------------------------------------
# Auth header helper
# ---------------------------------------------------------------------------

def auth_headers(token: str = FAKE_INTERNAL_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def encode_account_json(account_json: dict) -> str:
    """Return the base64-encoded JSON string for account_json."""
    return base64.b64encode(json.dumps(account_json).encode()).decode()


SAMPLE_ACCOUNT_JSON_B64 = encode_account_json(SAMPLE_ACCOUNT_JSON)
