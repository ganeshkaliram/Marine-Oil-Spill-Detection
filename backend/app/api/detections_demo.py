from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.schemas import AttributionReport, SlickDetection

router = APIRouter()


def _load_json(name: str):
    path = settings.DATA_PROCESSED_DIR / name
    if not path.is_file():
        return None
    return json.loads(path.read_text())


@router.get("/demo", response_model=list[SlickDetection])
def list_demo_detections() -> list[SlickDetection]:
    """Return slicks from the generated demo data (for scaffolding)."""
    data = _load_json("demo_slicks.json")
    if data is None:
        raise HTTPException(
            status_code=404,
            detail="No demo data. Run: python scripts/generate_demo_data.py",
        )
    return [SlickDetection(**d) for d in data]
