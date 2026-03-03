from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.auth.dependencies import get_current_credentials
from app.models.schemas import (
    BulkWriteRequest,
    FormatRequest,
    FormatResponse,
    SheetData,
    SheetInfo,
    SpreadsheetAllData,
    WriteCellRequest,
    WriteResponse,
    WriteRowsRequest,
)
from app.services.sheets import SheetsService

router = APIRouter(prefix="/sheets", tags=["sheets"])


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


@router.get("/{spreadsheet_id}", response_model=SpreadsheetAllData)
def read_all(
    spreadsheet_id: str,
    credentials=Depends(get_current_credentials),
) -> SpreadsheetAllData:
    """Return all data from all sheets in the spreadsheet."""
    svc = SheetsService(credentials)
    data = svc.read_all(spreadsheet_id)
    return SpreadsheetAllData(
        spreadsheet_id=data["spreadsheet_id"],
        title=data["title"],
        sheets=[SheetData(**s) for s in data["sheets"]],
    )


@router.get("/{spreadsheet_id}/sheets", response_model=list[SheetInfo])
def list_sheets(
    spreadsheet_id: str,
    credentials=Depends(get_current_credentials),
) -> list[SheetInfo]:
    """Return metadata for all sheets (name, sheetId, index)."""
    svc = SheetsService(credentials)
    return [SheetInfo(**s) for s in svc.list_sheets(spreadsheet_id)]


@router.get("/{spreadsheet_id}/read", response_model=SheetData)
def read_sheet(
    spreadsheet_id: str,
    sheet_name: str = Query(..., description="Sheet tab name"),
    credentials=Depends(get_current_credentials),
) -> SheetData:
    """Return all values from a specific sheet as a 2-D array."""
    svc = SheetsService(credentials)
    values = svc.read_sheet(spreadsheet_id, sheet_name)
    return SheetData(sheet_name=sheet_name, values=values)


@router.get("/{spreadsheet_id}/download")
def download(
    spreadsheet_id: str,
    format: str = Query("xlsx", description="Export format: xlsx, csv, pdf, ods, tsv"),
    credentials=Depends(get_current_credentials),
) -> Response:
    """Download the spreadsheet in the requested format."""
    svc = SheetsService(credentials)
    content, mime_type = svc.download(spreadsheet_id, format)
    ext = format.lower()
    filename = f"{spreadsheet_id}.{ext}"
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


@router.put("/{spreadsheet_id}/cell", response_model=WriteResponse)
def write_cell(
    spreadsheet_id: str,
    body: WriteCellRequest,
    credentials=Depends(get_current_credentials),
) -> WriteResponse:
    """Write a single value to a specific cell (1-based row/col)."""
    svc = SheetsService(credentials)
    result = svc.write_cell(
        spreadsheet_id,
        body.sheet_name,
        body.row,
        body.col,
        body.value,
    )
    return WriteResponse(**result)


@router.put("/{spreadsheet_id}/cells/bulk", response_model=dict)
def bulk_write(
    spreadsheet_id: str,
    body: BulkWriteRequest,
    credentials=Depends(get_current_credentials),
) -> dict:
    """Write multiple ranges in a single API call (batchUpdate)."""
    svc = SheetsService(credentials)
    return svc.bulk_write(spreadsheet_id, body.updates)


@router.put("/{spreadsheet_id}/rows", response_model=WriteResponse)
def write_rows(
    spreadsheet_id: str,
    body: WriteRowsRequest,
    credentials=Depends(get_current_credentials),
) -> WriteResponse:
    """Write one or more rows starting at start_row (1-based), column A."""
    svc = SheetsService(credentials)
    result = svc.write_rows(
        spreadsheet_id,
        body.sheet_name,
        body.start_row,
        body.rows,
    )
    return WriteResponse(**result)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


@router.put("/{spreadsheet_id}/format", response_model=FormatResponse)
def format_cells(
    spreadsheet_id: str,
    body: FormatRequest,
    credentials=Depends(get_current_credentials),
) -> FormatResponse:
    """Apply background color, text color, and/or bold to specified ranges."""
    svc = SheetsService(credentials)
    applied = svc.format_cells(spreadsheet_id, body.ranges)
    return FormatResponse(applied_ranges=applied)
