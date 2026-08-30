from __future__ import annotations

from fastapi import APIRouter

from app.ais.live import live_vessel_positions

router = APIRouter()


@router.get("/live")
def list_live_vessels() -> list[dict]:
    """Current live vessel positions for the monitoring map (MarineTraffic-style)."""
    return live_vessel_positions()
