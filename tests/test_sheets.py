from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.services.sheets import SheetsService, _cell_ref, _col_to_letter
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Utility function tests
# ---------------------------------------------------------------------------


class TestUtilFunctions:
    def test_col_to_letter_single(self) -> None:
        assert _col_to_letter(1) == "A"
        assert _col_to_letter(26) == "Z"

    def test_col_to_letter_double(self) -> None:
        assert _col_to_letter(27) == "AA"
        assert _col_to_letter(28) == "AB"
        assert _col_to_letter(52) == "AZ"
        assert _col_to_letter(53) == "BA"

    def test_cell_ref(self) -> None:
        assert _cell_ref(1, 1) == "A1"
        assert _cell_ref(5, 3) == "C5"
        assert _cell_ref(10, 26) == "Z10"
        assert _cell_ref(1, 27) == "AA1"


# ---------------------------------------------------------------------------
# SheetsService unit tests
# ---------------------------------------------------------------------------


def _make_sheets_service() -> tuple[SheetsService, MagicMock]:
    """Return (SheetsService instance, mock for the underlying google service)."""
    mock_creds = MagicMock()
    mock_creds.token = "fake-token"

    svc = SheetsService.__new__(SheetsService)
    svc._credentials = mock_creds

    mock_api = MagicMock()
    svc._service = mock_api
    return svc, mock_api


class TestSheetsServiceUnit:
    def test_list_sheets(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"sheetId": 0, "title": "Sheet1", "index": 0}},
                {"properties": {"sheetId": 12345, "title": "Data", "index": 1}},
            ]
        }
        result = svc.list_sheets("spreadsheet-id")
        assert len(result) == 2
        assert result[0] == {"sheet_id": 0, "title": "Sheet1", "index": 0}
        assert result[1] == {"sheet_id": 12345, "title": "Data", "index": 1}

    def test_read_sheet_returns_values(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [["A", "B"], ["1", "2"], ["3", "4"]]
        }
        result = svc.read_sheet("sid", "Sheet1")
        assert result == [["A", "B"], ["1", "2"], ["3", "4"]]

    def test_read_sheet_empty(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {}
        result = svc.read_sheet("sid", "Sheet1")
        assert result == []

    def test_read_all(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.get.return_value.execute.return_value = {
            "properties": {"title": "My Spreadsheet"},
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0, "index": 0}}],
        }
        mock_api.spreadsheets.return_value.values.return_value.batchGet.return_value.execute.return_value = {
            "valueRanges": [
                {"range": "Sheet1!A1:Z1000", "values": [["col1", "col2"], ["val1", "val2"]]}
            ]
        }
        result = svc.read_all("sid")
        assert result["title"] == "My Spreadsheet"
        assert len(result["sheets"]) == 1
        assert result["sheets"][0]["sheet_name"] == "Sheet1"
        assert result["sheets"][0]["values"][0] == ["col1", "col2"]

    def test_write_cell_uses_correct_range(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {
            "updatedRange": "Sheet1!C5",
            "updatedRows": 1,
            "updatedCells": 1,
        }
        result = svc.write_cell("sid", "Sheet1", row=5, col=3, value="Hello")
        assert result["updated_range"] == "Sheet1!C5"
        # Verify the range passed to API
        call_kwargs = mock_api.spreadsheets.return_value.values.return_value.update.call_args
        assert call_kwargs.kwargs["range"] == "Sheet1!C5"
        assert call_kwargs.kwargs["body"]["values"] == [["Hello"]]

    def test_bulk_write(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.values.return_value.batchUpdate.return_value.execute.return_value = {
            "totalUpdatedRows": 4,
            "totalUpdatedCells": 8,
            "responses": [{}],
        }
        from app.models.schemas import BulkWriteUpdate

        updates = [
            BulkWriteUpdate(sheet_name="Sheet1", range="A1:B2", values=[[1, 2], [3, 4]]),
            BulkWriteUpdate(sheet_name="Sheet2", range="C1:D2", values=[["a", "b"], ["c", "d"]]),
        ]
        result = svc.bulk_write("sid", updates)
        assert result["total_updated_rows"] == 4
        assert result["total_updated_cells"] == 8
        assert result["responses"] == 1

    def test_write_rows(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.values.return_value.update.return_value.execute.return_value = {
            "updatedRange": "Sheet1!A3:C4",
            "updatedRows": 2,
            "updatedCells": 6,
        }
        result = svc.write_rows("sid", "Sheet1", start_row=3, rows=[["a", "b", "c"], ["d", "e", "f"]])
        assert result["updated_rows"] == 2
        call_kwargs = mock_api.spreadsheets.return_value.values.return_value.update.call_args
        assert call_kwargs.kwargs["range"] == "Sheet1!A3:C4"

    def test_write_rows_empty(self) -> None:
        svc, mock_api = _make_sheets_service()
        result = svc.write_rows("sid", "Sheet1", start_row=1, rows=[])
        assert result["updated_rows"] == 0
        mock_api.spreadsheets.return_value.values.return_value.update.assert_not_called()

    def test_format_cells_background_color(self) -> None:
        svc, mock_api = _make_sheets_service()
        # Mock list_sheets to return sheet id
        mock_api.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"sheetId": 42, "title": "Sheet1", "index": 0}}]
        }
        mock_api.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}

        from app.models.schemas import Color, FormatRange

        fmt = FormatRange(
            sheet_name="Sheet1",
            start_row=1, end_row=1,
            background_color=Color(red=1.0, green=0.0, blue=0.0),
        )
        applied = svc.format_cells("sid", [fmt])
        assert applied == 1

        call_kwargs = mock_api.spreadsheets.return_value.batchUpdate.call_args
        requests = call_kwargs.kwargs["body"]["requests"]
        assert len(requests) == 1
        repeat_cell = requests[0]["repeatCell"]
        assert repeat_cell["range"]["sheetId"] == 42
        assert repeat_cell["range"]["startRowIndex"] == 0
        assert repeat_cell["range"]["endRowIndex"] == 1
        assert repeat_cell["cell"]["userEnteredFormat"]["backgroundColor"]["red"] == 1.0

    def test_format_cells_no_properties_skips(self) -> None:
        svc, mock_api = _make_sheets_service()
        mock_api.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "index": 0}}]
        }
        from app.models.schemas import FormatRange

        fmt = FormatRange(sheet_name="Sheet1")  # No colors, no bold
        applied = svc.format_cells("sid", [fmt])
        assert applied == 0
        mock_api.spreadsheets.return_value.batchUpdate.assert_not_called()

    def test_download_returns_bytes(self) -> None:
        svc, _ = _make_sheets_service()
        fake_content = b"PK\x03\x04fake-xlsx-content"
        with patch("app.services.sheets.http_requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = fake_content
            content, mime = svc.download("sid", "xlsx")
        assert content == fake_content
        assert "spreadsheetml" in mime

    def test_download_unsupported_format_raises_400(self) -> None:
        svc, _ = _make_sheets_service()
        with pytest.raises(HTTPException) as exc_info:
            svc.download("sid", "docx")
        assert exc_info.value.status_code == 400

    def test_download_api_error_raises_http(self) -> None:
        svc, _ = _make_sheets_service()
        with patch("app.services.sheets.http_requests.get") as mock_get:
            mock_get.return_value.status_code = 403
            mock_get.return_value.text = "Forbidden"
            with pytest.raises(HTTPException) as exc_info:
                svc.download("sid", "xlsx")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Sheets API endpoint tests
# ---------------------------------------------------------------------------


class TestSheetsEndpoints:
    SHEET_ID = "test-spreadsheet-id"

    async def test_read_all(self, client: AsyncClient) -> None:
        fake_data = {
            "spreadsheet_id": self.SHEET_ID,
            "title": "Test Spreadsheet",
            "sheets": [{"sheet_name": "Sheet1", "values": [["A", "B"], ["1", "2"]]}],
        }
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.read_all.return_value = fake_data
            resp = await client.get(f"/sheets/{self.SHEET_ID}", headers=auth_headers())

        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Spreadsheet"
        assert len(data["sheets"]) == 1

    async def test_list_sheets(self, client: AsyncClient) -> None:
        fake_sheets = [
            {"sheet_id": 0, "title": "Sheet1", "index": 0},
            {"sheet_id": 1, "title": "Data", "index": 1},
        ]
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.list_sheets.return_value = fake_sheets
            resp = await client.get(
                f"/sheets/{self.SHEET_ID}/sheets", headers=auth_headers()
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] == "Sheet1"

    async def test_read_sheet(self, client: AsyncClient) -> None:
        fake_values = [["col1", "col2"], ["val1", "val2"]]
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.read_sheet.return_value = fake_values
            resp = await client.get(
                f"/sheets/{self.SHEET_ID}/read",
                params={"sheet_name": "Sheet1"},
                headers=auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sheet_name"] == "Sheet1"
        assert data["values"] == fake_values

    async def test_download_xlsx(self, client: AsyncClient) -> None:
        fake_bytes = b"fake-xlsx-data"
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.download.return_value = (
                fake_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            resp = await client.get(
                f"/sheets/{self.SHEET_ID}/download",
                params={"format": "xlsx"},
                headers=auth_headers(),
            )

        assert resp.status_code == 200
        assert resp.content == fake_bytes
        assert "attachment" in resp.headers["content-disposition"]

    async def test_write_cell(self, client: AsyncClient) -> None:
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.write_cell.return_value = {
                "updated_range": "Sheet1!B3",
                "updated_rows": 1,
                "updated_cells": 1,
            }
            resp = await client.put(
                f"/sheets/{self.SHEET_ID}/cell",
                json={"sheet_name": "Sheet1", "row": 3, "col": 2, "value": "Hello"},
                headers=auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_range"] == "Sheet1!B3"

    async def test_bulk_write(self, client: AsyncClient) -> None:
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.bulk_write.return_value = {
                "total_updated_rows": 2,
                "total_updated_cells": 4,
                "responses": 1,
            }
            resp = await client.put(
                f"/sheets/{self.SHEET_ID}/cells/bulk",
                json={
                    "updates": [
                        {
                            "sheet_name": "Sheet1",
                            "range": "A1:B2",
                            "values": [[1, 2], [3, 4]],
                        }
                    ]
                },
                headers=auth_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["total_updated_rows"] == 2

    async def test_write_rows(self, client: AsyncClient) -> None:
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.write_rows.return_value = {
                "updated_range": "Sheet1!A5:C6",
                "updated_rows": 2,
                "updated_cells": 6,
            }
            resp = await client.put(
                f"/sheets/{self.SHEET_ID}/rows",
                json={
                    "sheet_name": "Sheet1",
                    "start_row": 5,
                    "rows": [["a", "b", "c"], ["d", "e", "f"]],
                },
                headers=auth_headers(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_rows"] == 2

    async def test_format_cells(self, client: AsyncClient) -> None:
        with patch("app.api.sheets.SheetsService") as MockSvc:
            MockSvc.return_value.format_cells.return_value = 2
            resp = await client.put(
                f"/sheets/{self.SHEET_ID}/format",
                json={
                    "ranges": [
                        {
                            "sheet_name": "Sheet1",
                            "start_row": 1,
                            "end_row": 1,
                            "background_color": {"red": 1.0, "green": 0.0, "blue": 0.0},
                        },
                        {
                            "sheet_name": "Sheet1",
                            "start_col": 1,
                            "end_col": 3,
                            "text_color": {"red": 0.0, "green": 0.0, "blue": 1.0},
                            "bold": True,
                        },
                    ]
                },
                headers=auth_headers(),
            )

        assert resp.status_code == 200
        assert resp.json()["applied_ranges"] == 2

    async def test_endpoints_require_auth(self, client: AsyncClient) -> None:
        """All sheets endpoints must reject requests without Authorization header."""
        endpoints = [
            ("GET", f"/sheets/{self.SHEET_ID}"),
            ("GET", f"/sheets/{self.SHEET_ID}/sheets"),
            ("GET", f"/sheets/{self.SHEET_ID}/download"),
            ("PUT", f"/sheets/{self.SHEET_ID}/cell"),
            ("PUT", f"/sheets/{self.SHEET_ID}/cells/bulk"),
            ("PUT", f"/sheets/{self.SHEET_ID}/rows"),
            ("PUT", f"/sheets/{self.SHEET_ID}/format"),
        ]
        for method, url in endpoints:
            resp = await client.request(method, url, json={})
            assert resp.status_code == 401, f"{method} {url} should return 401 without auth"
