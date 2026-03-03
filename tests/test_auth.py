from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.auth.token_manager import TokenManager
from tests.conftest import (
    FAKE_ACCESS_TOKEN,
    FAKE_EXPIRES_AT,
    FAKE_INTERNAL_TOKEN,
    SAMPLE_ACCOUNT_JSON,
    SAMPLE_ACCOUNT_JSON_B64,
    auth_headers,
    encode_account_json,
    make_mock_credentials,
)


# ---------------------------------------------------------------------------
# TokenManager unit tests (no HTTP)
# ---------------------------------------------------------------------------


class TestTokenManagerUnit:
    def test_register_new_account(self, token_manager: TokenManager) -> None:
        token = token_manager.register(SAMPLE_ACCOUNT_JSON)
        assert len(token) == 36  # UUID format
        assert "-" in token

    def test_register_same_account_returns_same_token(self, token_manager: TokenManager) -> None:
        token1 = token_manager.register(SAMPLE_ACCOUNT_JSON)
        token2 = token_manager.register(SAMPLE_ACCOUNT_JSON)
        assert token1 == token2

    def test_register_different_accounts_return_different_tokens(
        self, token_manager: TokenManager
    ) -> None:
        account2 = {**SAMPLE_ACCOUNT_JSON, "client_email": "other@project.iam.gserviceaccount.com"}
        token1 = token_manager.register(SAMPLE_ACCOUNT_JSON)
        token2 = token_manager.register(account2)
        assert token1 != token2

    def test_register_persists_to_disk(self, tmp_token_file: str) -> None:
        mgr1 = TokenManager(tmp_token_file)
        token = mgr1.register(SAMPLE_ACCOUNT_JSON)

        # Create a new manager pointing to same file
        mgr2 = TokenManager(tmp_token_file)
        token2 = mgr2.register(SAMPLE_ACCOUNT_JSON)
        assert token == token2

    def test_get_credentials_unknown_token_raises_401(
        self, token_manager: TokenManager
    ) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            token_manager.get_google_credentials("nonexistent-token")
        assert exc_info.value.status_code == 401

    def test_get_credentials_uses_cache(self, token_manager: TokenManager) -> None:
        token = token_manager.register(SAMPLE_ACCOUNT_JSON)
        mock_creds = make_mock_credentials()

        with patch("app.auth.token_manager.build_credentials", return_value=mock_creds):
            creds1 = token_manager.get_google_credentials(token)
            creds2 = token_manager.get_google_credentials(token)

        assert creds1 is creds2  # Same object from cache

    def test_get_credentials_refreshes_expired_cache(
        self, token_manager: TokenManager
    ) -> None:
        token = token_manager.register(SAMPLE_ACCOUNT_JSON)
        expired_creds = make_mock_credentials(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        fresh_creds = make_mock_credentials(token="fresh-token")

        with patch("app.auth.token_manager.build_credentials", return_value=expired_creds):
            token_manager.get_google_credentials(token)

        # Now the cache has expired credentials; next call should refresh
        with patch("app.auth.token_manager.build_credentials", return_value=fresh_creds) as mock_build:
            result = token_manager.get_google_credentials(token)

        assert result is fresh_creds
        mock_build.assert_called_once()

    def test_get_token_info_returns_access_token(self, token_manager: TokenManager) -> None:
        token = token_manager.register(SAMPLE_ACCOUNT_JSON)
        mock_creds = make_mock_credentials(token="my-access-token")

        with patch("app.auth.token_manager.build_credentials", return_value=mock_creds):
            info = token_manager.get_token_info(token)

        assert info["access_token"] == "my-access-token"
        assert info["expires_at"] is not None


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestAuthEndpoints:
    async def test_register_returns_internal_token(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/auth/register",
            json={"account_json_b64": SAMPLE_ACCOUNT_JSON_B64},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "internal_token" in data
        assert data["internal_token"] == FAKE_INTERNAL_TOKEN
        assert "message" in data

    async def test_register_same_account_idempotent(self, client_real_manager: AsyncClient) -> None:
        """Registering the same account twice returns the same token."""
        with patch("app.auth.token_manager.build_credentials"):
            resp1 = await client_real_manager.post(
                "/auth/register",
                json={"account_json_b64": SAMPLE_ACCOUNT_JSON_B64},
            )
            resp2 = await client_real_manager.post(
                "/auth/register",
                json={"account_json_b64": SAMPLE_ACCOUNT_JSON_B64},
            )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["internal_token"] == resp2.json()["internal_token"]

    async def test_register_different_accounts_different_tokens(
        self, client_real_manager: AsyncClient
    ) -> None:
        account2 = {**SAMPLE_ACCOUNT_JSON, "client_email": "other@other.iam.gserviceaccount.com"}
        with patch("app.auth.token_manager.build_credentials"):
            resp1 = await client_real_manager.post(
                "/auth/register", json={"account_json_b64": SAMPLE_ACCOUNT_JSON_B64}
            )
            resp2 = await client_real_manager.post(
                "/auth/register", json={"account_json_b64": encode_account_json(account2)}
            )
        assert resp1.json()["internal_token"] != resp2.json()["internal_token"]

    async def test_get_google_token_returns_access_token(self, client: AsyncClient) -> None:
        resp = await client.get("/auth/google-token", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == FAKE_ACCESS_TOKEN
        assert data["token_type"] == "Bearer"
        assert "expires_at" in data

    async def test_get_google_token_without_auth_returns_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/auth/google-token")
        assert resp.status_code == 401

    async def test_get_google_token_invalid_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        from fastapi import HTTPException

        # Make the mock raise 401
        from app.main import app as fastapi_app
        mgr = fastapi_app.state.token_manager
        mgr.get_google_credentials.side_effect = HTTPException(
            status_code=401, detail="Invalid or unknown internal token"
        )
        mgr.get_token_info.side_effect = HTTPException(
            status_code=401, detail="Invalid or unknown internal token"
        )

        resp = await client.get("/auth/google-token", headers=auth_headers("bad-token"))
        assert resp.status_code == 401

    async def test_register_invalid_base64_returns_400(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/auth/register",
            json={"account_json_b64": "not-valid-base64!!!"},
        )
        assert resp.status_code == 400

    async def test_register_valid_base64_but_invalid_json_returns_400(
        self, client: AsyncClient
    ) -> None:
        import base64
        bad_b64 = base64.b64encode(b"this is not json").decode()
        resp = await client.post(
            "/auth/register",
            json={"account_json_b64": bad_b64},
        )
        assert resp.status_code == 400
