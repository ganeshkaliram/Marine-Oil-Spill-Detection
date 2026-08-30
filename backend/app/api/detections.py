from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.schemas import SlickDetection
from app.detection.service import DetectionService

router = APIRouter()
service = DetectionService()


@router.get("/", response_model=list[SlickDetection])
def list_detections() -> list[SlickDetection]:
    """List all detected slicks currently in the pipeline."""
    return service.list_all()


@router.get("/scene/{scene_id}", response_model=list[SlickDetection])
def detect_scene(scene_id: str) -> list[SlickDetection]:
    """Run detection on a SAR scene and return any slicks found."""
    try:
        return service.run_detection(scene_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Scene '{scene_id}' not found in data/raw."
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@router.get("/{slick_id}", response_model=SlickDetection)
def get_detection(slick_id: str) -> SlickDetection:
    """Fetch a single slick by id."""
    slick = service.get(slick_id)
    if slick is None:
        raise HTTPException(status_code=404, detail=f"Slick '{slick_id}' not found.")
    return slick
