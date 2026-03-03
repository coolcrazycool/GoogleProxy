from __future__ import annotations

import string
from typing import Any

import requests as http_requests
from fastapi import HTTPException
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.models.schemas import BulkWriteUpdate, FormatRange


def _col_to_letter(col: int) -> str:
    """Convert 1-based column index to A1 letter(s). 1→A, 26→Z, 27→AA, …"""
    result = ""
    while col > 0:
        col, remainder = divmod(col - 1, 26)
        result = string.ascii_uppercase[remainder] + result
    return result


def _cell_ref(row: int, col: int) -> str:
    """Convert (1-based row, 1-based col) to A1 notation."""
    return f"{_col_to_letter(col)}{row}"


class SheetsService:
    """Wraps Google Sheets API v4 for all spreadsheet operations."""

    def __init__(self, credentials) -> None:
        self._service = build("sheets", "v4", credentials=credentials)
        self._credentials = credentials

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _handle_http_error(self, exc: HttpError) -> None:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"Sheets API error: {exc.reason}",
        ) from exc

    def _get_sheet_id(self, spreadsheet_id: str, sheet_name: str) -> int:
        """Resolve sheet name to its integer sheetId."""
        sheets = self.list_sheets(spreadsheet_id)
        for s in sheets:
            if s["title"] == sheet_name:
                return s["sheet_id"]
        raise HTTPException(
            status_code=404,
            detail=f"Sheet '{sheet_name}' not found in spreadsheet '{spreadsheet_id}'",
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_sheets(self, spreadsheet_id: str) -> list[dict]:
        """Return sheet metadata (sheet_id, title, index) for all sheets."""
        try:
            result = self._service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties",
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        return [
            {
                "sheet_id": s["properties"]["sheetId"],
                "title": s["properties"]["title"],
                "index": s["properties"]["index"],
            }
            for s in result.get("sheets", [])
        ]

    def read_sheet(self, spreadsheet_id: str, sheet_name: str) -> list[list[Any]]:
        """Return all values from a single sheet as a 2-D list."""
        try:
            result = self._service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=sheet_name,
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        return result.get("values", [])

    def read_all(self, spreadsheet_id: str) -> dict:
        """Return spreadsheet title + values for every sheet."""
        try:
            meta = self._service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="properties.title,sheets.properties",
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        title = meta["properties"]["title"]
        sheet_names = [s["properties"]["title"] for s in meta.get("sheets", [])]

        if not sheet_names:
            return {"spreadsheet_id": spreadsheet_id, "title": title, "sheets": []}

        try:
            batch = self._service.spreadsheets().values().batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=sheet_names,
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        sheets_data = []
        for vr in batch.get("valueRanges", []):
            # range key looks like "Sheet1!A1:Z1000"; take text before '!'
            range_label = vr.get("range", "")
            sname = range_label.split("!")[0].strip("'")
            sheets_data.append({"sheet_name": sname, "values": vr.get("values", [])})

        return {"spreadsheet_id": spreadsheet_id, "title": title, "sheets": sheets_data}

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    MIME_MAP: dict[str, str] = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "pdf": "application/pdf",
        "ods": "application/x-vnd.oasis.opendocument.spreadsheet",
        "tsv": "text/tab-separated-values",
    }

    def download(self, spreadsheet_id: str, fmt: str = "xlsx") -> tuple[bytes, str]:
        """
        Download the spreadsheet in *fmt* format.

        Returns (content_bytes, mime_type).
        """
        fmt = fmt.lower()
        mime_type = self.MIME_MAP.get(fmt)
        if mime_type is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format '{fmt}'. Supported: {list(self.MIME_MAP)}",
            )

        url = (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
            f"?format={fmt}"
        )
        resp = http_requests.get(
            url,
            headers={"Authorization": f"Bearer {self._credentials.token}"},
            timeout=60,
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Failed to download spreadsheet: {resp.text[:200]}",
            )
        return resp.content, mime_type

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def write_cell(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row: int,
        col: int,
        value: Any,
    ) -> dict:
        """Write a single value to the cell at (row, col) (1-based)."""
        cell = f"{sheet_name}!{_cell_ref(row, col)}"
        try:
            result = self._service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=cell,
                valueInputOption="USER_ENTERED",
                body={"values": [[value]]},
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        return {
            "updated_range": result.get("updatedRange"),
            "updated_rows": result.get("updatedRows"),
            "updated_cells": result.get("updatedCells"),
        }

    def bulk_write(self, spreadsheet_id: str, updates: list[BulkWriteUpdate]) -> dict:
        """Write multiple ranges in a single batchUpdate request."""
        data = [
            {
                "range": f"{u.sheet_name}!{u.range}",
                "values": u.values,
            }
            for u in updates
        ]
        try:
            result = self._service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": data,
                },
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        return {
            "total_updated_rows": result.get("totalUpdatedRows"),
            "total_updated_cells": result.get("totalUpdatedCells"),
            "responses": len(result.get("responses", [])),
        }

    def write_rows(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        start_row: int,
        rows: list[list[Any]],
    ) -> dict:
        """Write *rows* starting at *start_row* (1-based), column A."""
        if not rows:
            return {"updated_range": None, "updated_rows": 0, "updated_cells": 0}

        end_row = start_row + len(rows) - 1
        max_cols = max(len(r) for r in rows)
        end_col = _col_to_letter(max_cols)
        range_str = f"{sheet_name}!A{start_row}:{end_col}{end_row}"

        try:
            result = self._service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_str,
                valueInputOption="USER_ENTERED",
                body={"values": rows},
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        return {
            "updated_range": result.get("updatedRange"),
            "updated_rows": result.get("updatedRows"),
            "updated_cells": result.get("updatedCells"),
        }

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_cells(self, spreadsheet_id: str, ranges: list[FormatRange]) -> int:
        """
        Apply background/text color and bold formatting to the given ranges.

        Returns the number of batchUpdate requests applied.
        """
        sheet_cache: dict[str, int] = {}

        def _get_sid(name: str) -> int:
            if name not in sheet_cache:
                sheet_cache[name] = self._get_sheet_id(spreadsheet_id, name)
            return sheet_cache[name]

        requests_payload = []

        for fmt_range in ranges:
            sheet_id = _get_sid(fmt_range.sheet_name)

            # Build GridRange; None values mean "all rows/cols" (omit start/end)
            grid_range: dict = {"sheetId": sheet_id}
            if fmt_range.start_row is not None:
                grid_range["startRowIndex"] = fmt_range.start_row - 1  # 0-based
            if fmt_range.end_row is not None:
                grid_range["endRowIndex"] = fmt_range.end_row  # exclusive
            if fmt_range.start_col is not None:
                grid_range["startColumnIndex"] = fmt_range.start_col - 1
            if fmt_range.end_col is not None:
                grid_range["endColumnIndex"] = fmt_range.end_col

            # Build userEnteredFormat
            user_format: dict = {}
            fields_to_update: list[str] = []

            if fmt_range.background_color is not None:
                bc = fmt_range.background_color
                user_format["backgroundColor"] = {
                    "red": bc.red,
                    "green": bc.green,
                    "blue": bc.blue,
                }
                fields_to_update.append("backgroundColor")

            if fmt_range.text_color is not None or fmt_range.bold is not None:
                text_format: dict = {}
                if fmt_range.text_color is not None:
                    tc = fmt_range.text_color
                    text_format["foregroundColor"] = {
                        "red": tc.red,
                        "green": tc.green,
                        "blue": tc.blue,
                    }
                    fields_to_update.append("textFormat.foregroundColor")
                if fmt_range.bold is not None:
                    text_format["bold"] = fmt_range.bold
                    fields_to_update.append("textFormat.bold")
                user_format["textFormat"] = text_format

            if not fields_to_update:
                continue  # nothing to apply

            requests_payload.append({
                "repeatCell": {
                    "range": grid_range,
                    "cell": {"userEnteredFormat": user_format},
                    "fields": ",".join(fields_to_update),
                }
            })

        if not requests_payload:
            return 0

        try:
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests_payload},
            ).execute()
        except HttpError as exc:
            self._handle_http_error(exc)

        return len(requests_payload)
