from __future__ import annotations

"""
Integration tests that simulate a full user workflow:
  1. Register a service account → get internal_token
  2. Fetch Google token
  3. List spreadsheets
  4. Read a sheet
  5. Write a cell
  6. Bulk write
  7. Format a range

Google API calls are patched at the service layer so no network is required.
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_ACCOUNT_JSON, SAMPLE_ACCOUNT_JSON_B64, auth_headers, encode_account_json, make_mock_credentials


class TestFullWorkflow:
    async def test_register_and_use_api(self, client_real_manager: AsyncClient) -> None:
        mock_creds = make_mock_credentials()

        # 1. Register
        with patch("app.auth.token_manager.build_credentials", return_value=mock_creds):
            resp = await client_real_manager.post(
                "/auth/register", json={"account_json_b64": SAMPLE_ACCOUNT_JSON_B64}
            )
        assert resp.status_code == 200
        internal_token = resp.json()["internal_token"]
        assert len(internal_token) == 36

        headers = auth_headers(internal_token)

        # 2. Fetch Google token
        with patch("app.auth.token_manager.build_credentials", return_value=mock_creds):
            resp = await client_real_manager.get("/auth/google-token", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["access_token"] == mock_creds.token
        assert resp.json()["token_type"] == "Bearer"

        # 3. List spreadsheets
        fake_files = [{"id": "sid-1", "name": "My Sheet", "modified_time": "2024-01-01T00:00:00Z"}]
        with (
            patch("app.auth.token_manager.build_credentials", return_value=mock_creds),
            patch("app.api.drive.DriveService") as MockDrive,
        ):
            MockDrive.return_value.list_spreadsheets.return_value = fake_files
            resp = await client_real_manager.get("/drive/spreadsheets", headers=headers)
        assert resp.status_code == 200
        sheets = resp.json()
        assert sheets[0]["name"] == "My Sheet"
        spreadsheet_id = sheets[0]["id"]

        # 4. Read a sheet
        fake_values = [["Name", "Age"], ["Alice", "30"]]
        with (
            patch("app.auth.token_manager.build_credentials", return_value=mock_creds),
            patch("app.api.sheets.SheetsService") as MockSheets,
        ):
            MockSheets.return_value.read_sheet.return_value = fake_values
            resp = await client_real_manager.get(
                f"/sheets/{spreadsheet_id}/read",
                params={"sheet_name": "Sheet1"},
                headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json()["values"] == fake_values

        # 5. Write a cell
        with (
            patch("app.auth.token_manager.build_credentials", return_value=mock_creds),
            patch("app.api.sheets.SheetsService") as MockSheets,
        ):
            MockSheets.return_value.write_cell.return_value = {
                "updated_range": "Sheet1!A1",
                "updated_rows": 1,
                "updated_cells": 1,
            }
            resp = await client_real_manager.put(
                f"/sheets/{spreadsheet_id}/cell",
                json={"sheet_name": "Sheet1", "row": 1, "col": 1, "value": "New Value"},
                headers=headers,
            )
        assert resp.status_code == 200

        # 6. Bulk write
        with (
            patch("app.auth.token_manager.build_credentials", return_value=mock_creds),
            patch("app.api.sheets.SheetsService") as MockSheets,
        ):
            MockSheets.return_value.bulk_write.return_value = {
                "total_updated_rows": 2,
                "total_updated_cells": 6,
                "responses": 1,
            }
            resp = await client_real_manager.put(
                f"/sheets/{spreadsheet_id}/cells/bulk",
                json={
                    "updates": [
                        {"sheet_name": "Sheet1", "range": "A1:C2", "values": [["a", "b", "c"], ["d", "e", "f"]]}
                    ]
                },
                headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json()["total_updated_cells"] == 6

        # 7. Format a range
        with (
            patch("app.auth.token_manager.build_credentials", return_value=mock_creds),
            patch("app.api.sheets.SheetsService") as MockSheets,
        ):
            MockSheets.return_value.format_cells.return_value = 1
            resp = await client_real_manager.put(
                f"/sheets/{spreadsheet_id}/format",
                json={
                    "ranges": [
                        {
                            "sheet_name": "Sheet1",
                            "start_row": 1,
                            "end_row": 1,
                            "background_color": {"red": 0.2, "green": 0.8, "blue": 0.2},
                        }
                    ]
                },
                headers=headers,
            )
        assert resp.status_code == 200
        assert resp.json()["applied_ranges"] == 1

    async def test_same_account_always_same_token(
        self, client_real_manager: AsyncClient
    ) -> None:
        """Idempotency: registering the same account multiple times returns the same token."""
        mock_creds = make_mock_credentials()
        with patch("app.auth.token_manager.build_credentials", return_value=mock_creds):
            tokens = []
            for _ in range(3):
                resp = await client_real_manager.post(
                    "/auth/register", json={"account_json_b64": SAMPLE_ACCOUNT_JSON_B64}
                )
                assert resp.status_code == 200
                tokens.append(resp.json()["internal_token"])

        assert tokens[0] == tokens[1] == tokens[2]

    async def test_health_endpoint(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_find_spreadsheet_by_name_workflow(
        self, client_real_manager: AsyncClient
    ) -> None:
        mock_creds = make_mock_credentials()

        with patch("app.auth.token_manager.build_credentials", return_value=mock_creds):
            resp = await client_real_manager.post(
                "/auth/register", json={"account_json_b64": SAMPLE_ACCOUNT_JSON_B64}
            )
        token = resp.json()["internal_token"]

        with (
            patch("app.auth.token_manager.build_credentials", return_value=mock_creds),
            patch("app.api.drive.DriveService") as MockDrive,
        ):
            MockDrive.return_value.find_by_name.return_value = {
                "id": "abc123", "name": "Budget 2024"
            }
            resp = await client_real_manager.get(
                "/drive/spreadsheets/by-name",
                params={"name": "Budget 2024"},
                headers=auth_headers(token),
            )

        assert resp.status_code == 200
        assert resp.json()["id"] == "abc123"
