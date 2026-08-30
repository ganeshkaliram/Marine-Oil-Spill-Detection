from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.schemas import AttributionReport

router = APIRouter()


@router.get("/demo", response_model=list[AttributionReport])
def list_demo_reports() -> list[AttributionReport]:
    """Return attribution reports from generated demo data."""
    path = settings.DATA_PROCESSED_DIR / "demo_reports.json"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="No demo data. Run: python scripts/generate_demo_data.py",
        )
    data = json.loads(path.read_text())
    return [AttributionReport(**d) for d in data]
