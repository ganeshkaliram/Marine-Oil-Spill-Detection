from __future__ import annotations

import json
from statistics import mean
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.schemas import SlickDetection
from app.core.drift import backtrack_particles

router = APIRouter()


def _load_json(name: str) -> Any:
    path = settings.DATA_PROCESSED_DIR / name
    if not path.is_file():
        return None
    return json.loads(path.read_text())


@router.get("/demo/{slick_id}/backtrack")
def demo_backtrack(slick_id: str, hours: float = 12.0, n_particles: int = 500):
    """Backtrack a demo slick using the lightweight synthetic drift engine.

    Returns a particle cloud and a small summary (centroid, stddev).
    """
    data = _load_json("demo_slicks.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No demo data. Run: python scripts/generate_demo_data.py")

    slicks = [SlickDetection(**d) for d in data]
    slick = next((s for s in slicks if s.id == slick_id), None)
    if slick is None:
        raise HTTPException(status_code=404, detail=f"Slick id {slick_id} not found in demo data")

    particles = backtrack_particles(slick.geometry, hours=hours, n_particles=n_particles)
    lats = [p[0] for p in particles]
    lons = [p[1] for p in particles]

    summary = {
        "n_particles": len(particles),
        "origin_centroid": {"lat": mean(lats), "lon": mean(lons)},
        "lat_stddev": float(__import__("statistics").pstdev(lats)),
        "lon_stddev": float(__import__("statistics").pstdev(lons)),
    }

    return {"particles": [{"lat": float(lat), "lon": float(lon)} for lat, lon in particles], "summary": summary}
