from __future__ import annotations

from fastapi import HTTPException
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class DriveService:
    """Wraps Google Drive API v3 for spreadsheet discovery operations."""

    def __init__(self, credentials) -> None:
        self._service = build("drive", "v3", credentials=credentials)

    def list_spreadsheets(self) -> list[dict]:
        """Return all non-trashed spreadsheets accessible by the service account."""
        try:
            results = self._service.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                fields="files(id, name, modifiedTime)",
                pageSize=1000,
            ).execute()
            files = results.get("files", [])
            # Normalize key name for consistency
            return [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "modified_time": f.get("modifiedTime"),
                }
                for f in files
            ]
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Drive API error: {exc.reason}",
            ) from exc

    def find_by_name(self, name: str) -> dict:
        """Return first spreadsheet matching *name* exactly, or raise 404."""
        # Escape single quotes in name to avoid query injection
        safe_name = name.replace("'", "\\'")
        try:
            results = self._service.files().list(
                q=(
                    f"name='{safe_name}' "
                    "and mimeType='application/vnd.google-apps.spreadsheet' "
                    "and trashed=false"
                ),
                fields="files(id, name)",
            ).execute()
        except HttpError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Drive API error: {exc.reason}",
            ) from exc

        files = results.get("files", [])
        if not files:
            raise HTTPException(
                status_code=404,
                detail=f"Spreadsheet '{name}' not found on Drive",
            )
        return {"id": files[0]["id"], "name": files[0]["name"]}
