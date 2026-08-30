"""AIS vessel tracking API endpoints.

Endpoints:
    GET /api/v1/ais/live        — current vessel positions (REST, backward compat)
    GET /api/v1/ais/stream      — SSE stream of live positions (preferred)
    GET /api/v1/ais/positions   — current positions snapshot
    GET /api/v1/ais/status      — feed health and stats
    GET /api/v1/ais/vessels     — all known vessels with static data
    GET /api/v1/ais/vessels/{mmsi} — single vessel details
    GET /api/v1/ais/history/{mmsi} — position history for a vessel
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.ais.feed import get_feed_client
from app.ais.live import live_vessel_positions

router = APIRouter()


@router.get("/live")
def list_live_vessels() -> list[dict]:
    """Current live vessel positions for the monitoring map (MarineTraffic-style).

    Falls back to simulation when no real AIS feed is configured.
    """
    client = get_feed_client()
    if client.last_poll is not None and client.is_healthy:
        # Use real feed data
        return _tracks_to_positions(client.get_tracks())
    return live_vessel_positions()


@router.get("/vessels")
def list_vessels():
    """All known vessels with static metadata (name, type, cargo, destination, ETA)."""
    from app.core.db import get_db
    db = get_db()
    vessels = db.get_all_vessels()

    # Enrich with live position data
    client = get_feed_client()
    if client.last_poll is not None:
        tracks = {t.mmsi: t for t in client.get_tracks()}
        for v in vessels:
            t = tracks.get(v["mmsi"])
            if t and t.points:
                latest = max(t.points, key=lambda p: p.timestamp)
                v["lat"] = latest.lat
                v["lon"] = latest.lon
                v["sog_knots"] = latest.sog_knots
                v["cog_deg"] = latest.cog_deg
                v["trust_score"] = t.trust_score

    return vessels


@router.get("/vessels/{mmsi}")
def get_vessel(mmsi: int):
    """Get detailed data for a specific vessel by MMSI."""
    from app.core.db import get_db
    db = get_db()
    vessel = db.get_vessel(mmsi)
    if vessel is None:
        raise HTTPException(status_code=404, detail=f"Vessel MMSI {mmsi} not found")

    # Enrich with current track
    client = get_feed_client()
    for track in client.get_tracks():
        if track.mmsi == mmsi:
            vessel["current_track"] = {
                "trust_score": track.trust_score,
                "anomaly_count": len(track.anomalies),
                "point_count": len(track.points),
                "destination": track.destination,
                "eta": track.eta.isoformat() if track.eta else None,
                "cargo_type": track.cargo_type,
                "draft_dm": track.draft_dm,
            }
            if track.points:
                latest = max(track.points, key=lambda p: p.timestamp)
                vessel["current_position"] = {
                    "lat": latest.lat,
                    "lon": latest.lon,
                    "sog_knots": latest.sog_knots,
                    "cog_deg": latest.cog_deg,
                    "timestamp": latest.timestamp.isoformat(),
                }
            break

    return vessel


@router.get("/history/{mmsi}")
def get_vessel_history(
    mmsi: int,
    limit: int = Query(default=100, le=1000),
):
    """Get position history for a vessel."""
    from app.core.db import get_db
    db = get_db()
    positions = db.get_positions(mmsi=mmsi, limit=limit)
    if not positions:
        # Check if vessel exists at all
        vessel = db.get_vessel(mmsi)
        if vessel is None:
            raise HTTPException(status_code=404, detail=f"Vessel MMSI {mmsi} not found")
    return positions


def _tracks_to_positions(tracks) -> list[dict]:
    """Convert VesselTrack objects to position dicts for the API."""
    positions = []
    for track in tracks:
        if not track.points:
            continue
        latest = max(track.points, key=lambda p: p.timestamp)
        positions.append({
            "mmsi": track.mmsi,
            "name": track.vessel_name or f"Unknown ({track.mmsi})",
            "vessel_type": track.vessel_class.value if track.vessel_class else "other",
            "lat": latest.lat,
            "lon": latest.lon,
            "sog_knots": round(latest.sog_knots, 1),
            "cog_deg": round(latest.cog_deg, 0),
            "destination": track.destination,
            "eta": track.eta.isoformat() if track.eta else None,
            "cargo_type": track.cargo_type,
            "trust_score": round(track.trust_score, 2),
            "anomaly_count": len(track.anomalies),
            "updated_at": latest.timestamp.isoformat(),
        })
    return positions
