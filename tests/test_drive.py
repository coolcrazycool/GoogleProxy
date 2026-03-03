from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.services.drive import DriveService
from tests.conftest import auth_headers

FAKE_FILES = [
    {"id": "id-1", "name": "Budget 2024", "modified_time": "2024-01-15T10:00:00Z"},
    {"id": "id-2", "name": "Quarterly Report", "modified_time": "2024-02-01T08:30:00Z"},
]


# ---------------------------------------------------------------------------
# DriveService unit tests
# ---------------------------------------------------------------------------


class TestDriveServiceUnit:
    def _make_service(self, list_return: dict) -> DriveService:
        mock_creds = MagicMock()
        svc = DriveService.__new__(DriveService)

        mock_files = MagicMock()
        mock_files.list.return_value.execute.return_value = list_return
        mock_drive = MagicMock()
        mock_drive.files.return_value = mock_files
        svc._service = mock_drive
        return svc

    def test_list_spreadsheets_returns_normalized_list(self) -> None:
        raw = {
            "files": [
                {"id": "id-1", "name": "Sheet1", "modifiedTime": "2024-01-01T00:00:00Z"},
                {"id": "id-2", "name": "Sheet2", "modifiedTime": None},
            ]
        }
        svc = self._make_service(raw)
        result = svc.list_spreadsheets()
        assert len(result) == 2
        assert result[0] == {"id": "id-1", "name": "Sheet1", "modified_time": "2024-01-01T00:00:00Z"}
        assert result[1]["modified_time"] is None

    def test_list_spreadsheets_empty(self) -> None:
        svc = self._make_service({"files": []})
        assert svc.list_spreadsheets() == []

    def test_find_by_name_found(self) -> None:
        svc = self._make_service({"files": [{"id": "id-x", "name": "My Sheet"}]})
        result = svc.find_by_name("My Sheet")
        assert result == {"id": "id-x", "name": "My Sheet"}

    def test_find_by_name_not_found_raises_404(self) -> None:
        svc = self._make_service({"files": []})
        with pytest.raises(HTTPException) as exc_info:
            svc.find_by_name("Nonexistent")
        assert exc_info.value.status_code == 404

    def test_find_by_name_returns_first_match(self) -> None:
        svc = self._make_service({
            "files": [
                {"id": "id-first", "name": "Duplicate"},
                {"id": "id-second", "name": "Duplicate"},
            ]
        })
        result = svc.find_by_name("Duplicate")
        assert result["id"] == "id-first"


# ---------------------------------------------------------------------------
# Drive API endpoint tests
# ---------------------------------------------------------------------------


class TestDriveEndpoints:
    async def test_list_spreadsheets(self, client: AsyncClient) -> None:
        with patch("app.api.drive.DriveService") as MockDrive:
            MockDrive.return_value.list_spreadsheets.return_value = FAKE_FILES
            resp = await client.get("/drive/spreadsheets", headers=auth_headers())

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "id-1"
        assert data[0]["name"] == "Budget 2024"

    async def test_list_spreadsheets_unauthorized(self, client: AsyncClient) -> None:
        resp = await client.get("/drive/spreadsheets")
        assert resp.status_code == 401

    async def test_find_by_name_found(self, client: AsyncClient) -> None:
        with patch("app.api.drive.DriveService") as MockDrive:
            MockDrive.return_value.find_by_name.return_value = {
                "id": "id-1", "name": "Budget 2024"
            }
            resp = await client.get(
                "/drive/spreadsheets/by-name",
                params={"name": "Budget 2024"},
                headers=auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "id-1"
        assert data["name"] == "Budget 2024"

    async def test_find_by_name_not_found(self, client: AsyncClient) -> None:
        with patch("app.api.drive.DriveService") as MockDrive:
            MockDrive.return_value.find_by_name.side_effect = HTTPException(
                status_code=404, detail="Spreadsheet 'X' not found on Drive"
            )
            resp = await client.get(
                "/drive/spreadsheets/by-name",
                params={"name": "X"},
                headers=auth_headers(),
            )

        assert resp.status_code == 404
