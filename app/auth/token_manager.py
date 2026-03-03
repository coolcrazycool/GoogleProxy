from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

from app.services.google_auth import build_credentials


def _hash_account(account_json: dict) -> str:
    """Return a stable SHA-256 hex digest for the account JSON (key-order independent)."""
    serialized = json.dumps(account_json, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


# Refresh the token 60 seconds before actual expiry to avoid using stale tokens.
_REFRESH_BUFFER_SECONDS = 60


class TokenManager:
    """
    Manages two levels of token state:

    - **Disk** (JSON file): maps internal_token (UUID) → {account_json, account_hash, created_at}.
      Survives server restarts.

    - **Memory** (dict): maps internal_token → {credentials, expires_at}.
      Lost on restart; rebuilt lazily on first request after restart.
    """

    def __init__(self, storage_path: str) -> None:
        self._path = Path(storage_path)
        self._cache: dict[str, dict] = {}  # internal_token → {credentials, expires_at}
        self._lock = threading.Lock()
        self._ensure_storage()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, account_json: dict) -> str:
        """
        Register a service account.  Returns the stable internal UUID token.
        If the same account was registered before (identified by SHA-256 hash),
        the existing token is returned unchanged.
        """
        account_hash = _hash_account(account_json)
        with self._lock:
            data = self._load()
            for token, record in data["tokens"].items():
                if record.get("account_hash") == account_hash:
                    return token
            internal_token = str(uuid.uuid4())
            data["tokens"][internal_token] = {
                "account_json": account_json,
                "account_hash": account_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save(data)
            return internal_token

    def get_google_credentials(self, internal_token: str):
        """
        Return valid Google credentials for *internal_token*.

        - Raises HTTP 401 if the token is unknown.
        - Returns cached credentials if still valid.
        - Refreshes (re-builds) credentials if expired or missing from cache.
        """
        with self._lock:
            data = self._load()
            if internal_token not in data["tokens"]:
                raise HTTPException(status_code=401, detail="Invalid or unknown internal token")

            cached = self._cache.get(internal_token)
            if cached is not None:
                expires_at: datetime = cached["expires_at"]
                now = datetime.now(timezone.utc)
                # Make expires_at timezone-aware if needed
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if now < expires_at - timedelta(seconds=_REFRESH_BUFFER_SECONDS):
                    return cached["credentials"]

            # Refresh
            account_json = data["tokens"][internal_token]["account_json"]
            creds = build_credentials(account_json)
            expiry = creds.expiry
            if expiry is not None and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            self._cache[internal_token] = {
                "credentials": creds,
                "expires_at": expiry or datetime.now(timezone.utc) + timedelta(hours=1),
            }
            return creds

    def get_token_info(self, internal_token: str) -> dict:
        """
        Return {access_token, expires_at} for *internal_token*.
        Triggers credential refresh if needed.
        """
        creds = self.get_google_credentials(internal_token)
        expiry = creds.expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return {
            "access_token": creds.token,
            "expires_at": expiry.isoformat() if expiry else None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_storage(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text(json.dumps({"tokens": {}}, indent=2), encoding="utf-8")

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"tokens": {}}

    def _save(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
