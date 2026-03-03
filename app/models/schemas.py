from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    account_json_b64: str = Field(
        ..., description="Base64-encoded Google service account JSON"
    )


class RegisterResponse(BaseModel):
    internal_token: str = Field(..., description="Stable internal UUID token for this account")
    message: str


class GoogleTokenResponse(BaseModel):
    access_token: str
    expires_at: str = Field(..., description="ISO-8601 UTC expiry time")
    token_type: str = "Bearer"


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

class SpreadsheetMeta(BaseModel):
    id: str
    name: str
    modified_time: Optional[str] = None


class SpreadsheetByNameResponse(BaseModel):
    id: str
    name: str


# ---------------------------------------------------------------------------
# Sheets — metadata
# ---------------------------------------------------------------------------

class SheetInfo(BaseModel):
    sheet_id: int
    title: str
    index: int


class SheetData(BaseModel):
    sheet_name: str
    values: list[list[Any]]


class SpreadsheetAllData(BaseModel):
    spreadsheet_id: str
    title: str
    sheets: list[SheetData]


# ---------------------------------------------------------------------------
# Sheets — write operations
# ---------------------------------------------------------------------------

class WriteCellRequest(BaseModel):
    sheet_name: str
    row: int = Field(..., ge=1, description="1-based row index")
    col: int = Field(..., ge=1, description="1-based column index")
    value: Any


class BulkWriteUpdate(BaseModel):
    sheet_name: str
    range: str = Field(..., description="A1 notation range, e.g. 'A1:C3'")
    values: list[list[Any]]


class BulkWriteRequest(BaseModel):
    updates: list[BulkWriteUpdate]


class WriteRowsRequest(BaseModel):
    sheet_name: str
    start_row: int = Field(..., ge=1, description="1-based row index to start writing from")
    rows: list[list[Any]]


class WriteResponse(BaseModel):
    updated_range: Optional[str] = None
    updated_rows: Optional[int] = None
    updated_cells: Optional[int] = None


# ---------------------------------------------------------------------------
# Sheets — formatting
# ---------------------------------------------------------------------------

class Color(BaseModel):
    red: float = Field(0.0, ge=0.0, le=1.0)
    green: float = Field(0.0, ge=0.0, le=1.0)
    blue: float = Field(0.0, ge=0.0, le=1.0)


class FormatRange(BaseModel):
    sheet_name: str
    start_row: Optional[int] = Field(None, ge=1, description="1-based; None = all rows")
    end_row: Optional[int] = Field(None, ge=1, description="1-based inclusive; None = all rows")
    start_col: Optional[int] = Field(None, ge=1, description="1-based; None = all cols")
    end_col: Optional[int] = Field(None, ge=1, description="1-based inclusive; None = all cols")
    background_color: Optional[Color] = None
    text_color: Optional[Color] = None
    bold: Optional[bool] = None


class FormatRequest(BaseModel):
    ranges: list[FormatRange]


class FormatResponse(BaseModel):
    applied_ranges: int
