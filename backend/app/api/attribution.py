from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.attribution.service import AttributionService
from app.core.schemas import AttributionReport, SlickDetection
from app.detection.service import DetectionService

router = APIRouter()
service = AttributionService()
detection_service = DetectionService()


@router.post("/{slick_id}", response_model=AttributionReport)
def attribute_slick(slick_id: str, body: list[SlickDetection] | None = None) -> AttributionReport:
    """Attribute a slick to suspect vessels.

    The request body optionally carries AIS track patches; otherwise the service
    relies on its in-memory/DB store of cleaned tracks.
    """
    slick = detection_service.get(slick_id)
    if slick is None:
        raise HTTPException(status_code=404, detail=f"Slick '{slick_id}' not found.")

    # Tracks will be pulled from the AIS store once wired.
    try:
        from app.ais.store import in_memory_tracks
    except ImportError:
        in_memory_tracks = []

    return service.attribute(slick, in_memory_tracks)
