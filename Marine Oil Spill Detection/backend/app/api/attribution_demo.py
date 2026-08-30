from __future__ import annotations

import json
from typing import Iterable

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.schemas import AttributionReport, SlickDetection, VesselTrack
from app.attribution.service import AttributionService

router = APIRouter()


def _load_json(name: str):
    path = settings.DATA_PROCESSED_DIR / name
    if not path.is_file():
        return None
    return json.loads(path.read_text())


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


@router.get("/demo/{slick_id}/compute", response_model=AttributionReport)
def compute_attribution(slick_id: str) -> AttributionReport:
    """Compute attribution for a demo slick by running the AttributionService on
    demo tracks. The computed report is returned and written back to
    data/processed/demo_reports.json (replacing or appending the record).
    """
    slicks_data = _load_json("demo_slicks.json")
    tracks_data = _load_json("demo_tracks.json")
    if slicks_data is None or tracks_data is None:
        raise HTTPException(status_code=404, detail="Demo slicks or tracks missing; run scripts/generate_demo_data.py")

    slicks = [SlickDetection(**d) for d in slicks_data]
    slick = next((s for s in slicks if s.id == slick_id), None)
    if slick is None:
        raise HTTPException(status_code=404, detail=f"Slick id {slick_id} not found")

    tracks = [VesselTrack(**t) for t in tracks_data]

    service = AttributionService()
    report = service.attribute(slick, tracks)

    # persist report (replace existing with same slick_id)
    path = settings.DATA_PROCESSED_DIR / "demo_reports.json"
    reports = []
    if path.is_file():
        reports = json.loads(path.read_text())
        # remove any existing for this slick
        reports = [r for r in reports if r.get("slick_id") != slick_id]
    reports.append(report.model_dump(mode="json"))
    path.write_text(json.dumps(reports, indent=2))

    return report
