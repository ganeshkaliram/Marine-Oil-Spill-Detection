"""Real-time monitoring service.

Runs continuously on your machine (or a VM) and orchestrates the pipeline on a
timer:

    poll new AIS + SAR scene -> detect spills -> analyse vessels -> attribute
    -> publish live results to database and live state JSON

Supports:
- Real AIS feeds via HTTP polling (configured via AIS_FEED_URL)
- Automatic fallback to synthetic simulation when feed unavailable
- Anomaly detection and spoof filtering on all incoming AIS data
- SQLite persistence for tracks, attribution, and events
- SSE broadcasting to connected dashboard clients

Usage:
    python scripts/monitor_service.py            # start and run forever
    python scripts/monitor_service.py --once     # single pass, for tests
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from app.ais.feed import AisFeedClient, get_feed_client
from app.ais.live import live_vessel_positions
from app.attribution.service import AttributionService
from app.config import settings
from app.core.db import get_db
from app.core.schemas import AisMessage, AisStaticData
from app.core.utils import gen_id, utcnow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monitor")

POLL_INTERVAL_SEC = 60


class LiveStateStore:
    """Publishes the current live state to both JSON file and SQLite database."""

    LOG = settings.DATA_PROCESSED_DIR / "live_state.json"
    LOG.parent.mkdir(parents=True, exist_ok=True)

    def __init__(self):
        self._db = get_db()

    def publish(self, slicks: list, reports: list, events: list, positions: list[dict] | None = None) -> None:
        """Write live state to both JSON file and database."""
        state = {
            "updated_at": utcnow().isoformat(),
            "active_spills": [s.model_dump(mode="json") for s in slicks],
            "attribution": [r.model_dump(mode="json") for r in reports],
            "recent_events": events[-20:],
            "live_positions": positions or [],
        }

        # Write JSON file (for backward compat / Vercel demo)
        self.LOG.write_text(json.dumps(state, indent=2))

        # Write to database
        self._db.save_live_state(state)

        # Store events
        for evt in events:
            self._db.insert_event(evt)

        # Store attribution reports
        for rep in reports:
            self._db.insert_attribution(rep)


def _get_feed_positions() -> list[AisMessage]:
    """Try to get positions from the real AIS feed. Falls back to simulation."""
    if not settings.AIS_FEED_URL:
        return []

    client = get_feed_client()
    try:
        result = client.poll_once()
        if "error" in result:
            logger.warning("Feed poll error: %s", result["error"])
            return []
        # Feed client accumulates messages internally
        # We need to get the latest batch
        return client._position_buffer[-200:] if client._position_buffer else []
    except Exception as e:
        logger.warning("Feed unavailable, will use simulation: %s", e)
        return []


def _get_simulated_positions() -> list[dict]:
    """Get simulated vessel positions."""
    return live_vessel_positions()


def _simulated_positions_to_messages(positions: list[dict]) -> list[AisMessage]:
    """Convert simulated position dicts to AisMessage objects for attribution."""
    from app.core.schemas import AisVesselClass
    messages = []
    for p in positions:
        vc = AisVesselClass(p["vessel_type"]) if p["vessel_type"] in AisVesselClass.__members__.values() else AisVesselClass.OTHER
        messages.append(AisMessage(
            mmsi=p["mmsi"],
            timestamp=utcnow(),
            lat=p["lat"],
            lon=p["lon"],
            sog_knots=p["sog_knots"],
            cog_deg=p["cog_deg"],
            vessel_class=vc,
            vessel_name=p.get("name"),
            destination=p.get("destination"),
            cargo_type=p.get("cargo_type"),
        ))
    return messages


def run_once() -> dict:
    """One full pipeline pass. Returns summary counts for tests/logging."""
    db = get_db()
    store = LiveStateStore()
    attribution_service = AttributionService()

    # --- Phase 1: Ingest AIS data --- #
    feed_client = None
    real_positions = []
    simulated = False

    if settings.AIS_FEED_URL:
        feed_client = get_feed_client()
        result = feed_client.poll_once()
        if "error" not in result:
            real_positions = feed_client._position_buffer[-500:]
            logger.info(
                "AIS feed: %d positions, %d tracks, %d static vessels",
                result.get("positions", 0),
                result.get("tracks", 0),
                len(feed_client.get_all_static_data()),
            )
        else:
            logger.warning("Feed error: %s — falling back to simulation", result["error"])
            simulated = True
    else:
        simulated = True

    if simulated:
        if settings.AIS_FALLBACK_TO_SIMULATION:
            logger.info("Using simulated vessel positions")
            sim_pos = _get_simulated_positions()
            real_positions = _simulated_positions_to_messages(sim_pos)
        else:
            logger.warning("No AIS feed configured and simulation disabled")
            real_positions = []

    # --- Phase 2: Store positions in database --- #
    if real_positions:
        count = db.insert_positions(real_positions)
        logger.debug("Stored %d positions in database", count)

    # --- Phase 2b: Build tracks with anomaly detection --- #
    from app.ais.service import AisProcessingService
    processor = AisProcessingService()
    tracks = processor.build_tracks(real_positions)

    # Enrich tracks with static data
    if feed_client:
        for track in tracks:
            static = feed_client.get_static_data(track.mmsi)
            if static:
                track.vessel_name = static.vessel_name or track.vessel_name
                track.destination = static.destination
                track.eta = static.eta
                track.cargo_type = static.cargo_type
                track.draft_dm = static.draft_dm
                track.ship_length_m = static.ship_length_m
                track.ship_breadth_m = static.ship_breadth_m

    # Store tracks
    if tracks:
        db.replace_tracks(tracks)
        # Also store static data
        if feed_client:
            for static in feed_client.get_all_static_data().values():
                db.upsert_vessel(static)

    # --- Phase 3: Generate synthetic slicks for demo (replace with real SAR) --- #
    from generate_demo_data import build_slicks
    slicks = build_slicks()

    # --- Phase 4: Attribution --- #
    reports = [attribution_service.attribute(s, tracks) for s in slicks]

    # --- Phase 5: Build events --- #
    events = []
    for r in reports:
        # Check for spoofed tracks
        spoofed_count = sum(1 for t in tracks if t.trust_score < settings.AIS_SPOOF_SCORE_THRESHOLD)

        event_msg = (
            f"ALERT Spill {r.slick_id} -> suspected vessel "
            f"{r.top_suspect.vessel_name or r.top_suspect.mmsi} "
            f"({r.top_suspect.correlation_score*100:.0f}%)"
            if r.top_suspect
            else f"Spill {r.slick_id} - no suspect in window"
        )

        events.append({
            "id": gen_id("evt"),
            "time": utcnow().isoformat(),
            "event_type": "spill_attribution",
            "slick_id": r.slick_id,
            "message": event_msg,
            "details": {
                "spoofed_tracks_filtered": spoofed_count,
                "total_tracks": len(tracks),
                "feed_source": "real" if not simulated else "simulated",
            },
        })

    if simulated:
        events.append({
            "id": gen_id("evt"),
            "time": utcnow().isoformat(),
            "event_type": "info",
            "message": "Running in simulation mode — configure AIS_FEED_URL for live data",
            "details": {"mode": "simulation"},
        })

    # --- Phase 6: Publish --- #
    positions_for_api = []
    if simulated:
        positions_for_api = _get_simulated_positions()
    elif feed_client:
        from app.api.ais_stream import _tracks_to_positions
        positions_for_api = _tracks_to_positions(feed_client.get_tracks())

    store.publish(slicks, reports, events, positions_for_api)

    # Try to broadcast via SSE if available
    try:
        from app.api.ais_stream import broadcast_vessels, broadcast_alert
        if positions_for_api:
            broadcast_vessels(positions_for_api)
        for evt in events:
            if evt.get("event_type") == "spill_attribution":
                broadcast_alert(evt)
    except ImportError:
        pass  # SSE not available (running outside FastAPI)

    return {
        "slicks": len(slicks),
        "reports": len(reports),
        "events": len(events),
        "tracks": len(tracks),
        "positions": len(real_positions),
        "spoofed_filtered": sum(1 for t in tracks if t.trust_score < settings.AIS_SPOOF_SCORE_THRESHOLD),
        "feed": "real" if not simulated else "simulated",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Oil spill real-time monitor")
    parser.add_argument("--once", action="store_true", help="run a single pass")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL_SEC,
                        help="poll interval in seconds")
    args = parser.parse_args()

    logger.info("== Marine Oil Spill Monitoring Service ==")
    logger.info("   live state -> %s", LiveStateStore.LOG)
    logger.info("   database   -> %s", settings.DATA_PROCESSED_DIR / "maritime.db")

    if settings.AIS_FEED_URL:
        logger.info("   AIS feed   -> %s", settings.AIS_FEED_URL)
    else:
        logger.info("   AIS feed   -> synthetic (configure AIS_FEED_URL for live data)")

    # Initialize database
    get_db()

    if args.once:
        summary = run_once()
        logger.info("   one-time pass: %s", summary)
        return

    # Start AIS feed client in background if configured
    if settings.AIS_FEED_URL:
        client = get_feed_client()
        client.start()

    logger.info("   polling every %ds (Ctrl+C to stop)", args.interval)
    try:
        while True:
            try:
                summary = run_once()
                logger.info("   pass -> %s", summary)
            except Exception as exc:
                logger.error("   ERROR: %s", exc, exc_info=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("   shutting down")
        if settings.AIS_FEED_URL:
            get_feed_client().stop()


if __name__ == "__main__":
    main()
