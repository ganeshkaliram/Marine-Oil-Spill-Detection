"""Server-Sent Events (SSE) endpoint for real-time AIS vessel tracking.

Replaces the polling-based /api/v1/ais/live endpoint with a persistent
connection that pushes vessel positions as they arrive from the AIS feed.

Frontend connects via EventSource and receives:
- "vessel_update" — position update for one or more vessels
- "static_update" — vessel metadata (name, type, destination, ETA, cargo)
- "alert"         — anomaly/spoofing detection or spill correlation event
- "heartbeat"     — keep-alive every 15s

This is more efficient than REST polling for real-time dashboards because:
1. No repeated HTTP handshakes
2. Data arrives as soon as it's available (push, not poll)
3. Lower latency for commodity traders making time-sensitive decisions
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.ais.feed import get_feed_client
from app.ais.live import live_vessel_positions
from app.config import settings
from app.core.schemas import AisMessage, AisStaticData

logger = logging.getLogger(__name__)
router = APIRouter()

# Broadcast queues — one per connected SSE client
_subscribers: list[queue.Queue] = []
_sub_lock = threading.Lock()


def broadcast_vessels(vessels: list[dict]) -> None:
    """Push vessel positions to all connected SSE clients."""
    event = {
        "type": "vessel_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": vessels,
    }
    _push_event(event)


def broadcast_static(static: dict) -> None:
    """Push static vessel data to all connected SSE clients."""
    event = {
        "type": "static_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": static,
    }
    _push_event(event)


def broadcast_alert(alert: dict) -> None:
    """Push an alert event to all connected SSE clients."""
    event = {
        "type": "alert",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": alert,
    }
    _push_event(event)


def _push_event(event: dict) -> None:
    """Send an event to all subscriber queues, dropping slow clients."""
    dead = []
    with _sub_lock:
        for q in _subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                dead.append(q)
        # Remove full (likely disconnected) queues
        for q in dead:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass


def _subscribe() -> queue.Queue:
    """Subscribe to SSE events. Returns a queue that receives events."""
    q: queue.Queue = queue.Queue(maxsize=200)
    with _sub_lock:
        _subscribers.append(q)
    return q


def _unsubscribe(q: queue.Queue) -> None:
    """Unsubscribe from SSE events."""
    with _sub_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


@router.get("/stream")
async def vessel_stream(request: Request):
    """SSE endpoint: GET /api/v1/ais/stream

    Connect with:
        const es = new EventSource('/api/v1/ais/stream');
        es.onmessage = (e) => { const data = JSON.parse(e.data); ... };

    Or use the data channel:
        es.addEventListener('vessel_update', (e) => { ... });
        es.addEventListener('static_update', (e) => { ... });
        es.addEventListener('alert', (e) => { ... });
    """
    q = _subscribe()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    event = q.get(timeout=15.0)
                    event_type = event.get("type", "message")
                    payload = json.dumps(event, default=str)
                    yield f"event: {event_type}\ndata: {payload}\n\n"
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    heartbeat = json.dumps({
                        "type": "heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "connected_clients": len(_subscribers),
                    })
                    yield f"event: heartbeat\ndata: {heartbeat}\n\n"
        finally:
            _unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("/positions")
def get_positions_snapshot() -> list[dict]:
    """Fallback REST endpoint: current vessel positions (snapshot).

    Use /stream for real-time updates. This endpoint exists for:
    - Initial page load (get current state before SSE connects)
    - Vercel serverless functions that can't do SSE
    - Debugging / API consumers
    """
    client = get_feed_client()
    if client.last_poll is not None and client.is_healthy:
        # Use real feed data if available
        return _tracks_to_positions(client.get_tracks())
    # Fallback to simulation
    return live_vessel_positions()


@router.get("/status")
def feed_status() -> dict:
    """AIS feed health and statistics."""
    client = get_feed_client()
    from app.core.db import get_db
    db = get_db()

    return {
        "feed_healthy": client.is_healthy,
        "last_poll": client.last_poll.isoformat() if client.last_poll else None,
        "feed_url": client.feed_url or "(synthetic)",
        "poll_interval_sec": client.poll_interval,
        "subscriber_count": len(_subscribers),
        "db_stats": db.get_stats(),
    }


def _tracks_to_positions(tracks) -> list[dict]:
    """Convert VesselTrack objects to position dicts for the API."""
    from app.ais.nmea import NmeaAisParser
    parser = NmeaAisParser()
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
