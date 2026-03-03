from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_credentials
from app.models.schemas import SpreadsheetByNameResponse, SpreadsheetMeta
from app.services.drive import DriveService

router = APIRouter(prefix="/drive", tags=["drive"])


@router.get("/spreadsheets", response_model=list[SpreadsheetMeta])
def list_spreadsheets(
    credentials=Depends(get_current_credentials),
) -> list[SpreadsheetMeta]:
    """List all Google Spreadsheets accessible by the service account."""
    svc = DriveService(credentials)
    files = svc.list_spreadsheets()
    return [SpreadsheetMeta(**f) for f in files]


@router.get("/spreadsheets/by-name", response_model=SpreadsheetByNameResponse)
def find_spreadsheet_by_name(
    name: str,
    credentials=Depends(get_current_credentials),
) -> SpreadsheetByNameResponse:
    """Find a spreadsheet by its exact name and return its ID."""
    svc = DriveService(credentials)
    result = svc.find_by_name(name)
    return SpreadsheetByNameResponse(**result)
