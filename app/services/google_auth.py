from __future__ import annotations

import google.auth.transport.requests
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def build_credentials(account_json: dict) -> service_account.Credentials:
    """Build and refresh Google service account credentials from account JSON dict."""
    creds = service_account.Credentials.from_service_account_info(
        account_json, scopes=SCOPES
    )
    request = google.auth.transport.requests.Request()
    creds.refresh(request)
    return creds
