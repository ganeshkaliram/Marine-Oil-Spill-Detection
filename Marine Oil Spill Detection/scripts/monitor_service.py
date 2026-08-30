"""Real-time monitoring service.

Runs continuously on your machine (or a VM) and orchestrates the pipeline on a
timer:

    poll new AIS + SAR scene -> detect spills -> analyse vessels -> attribute
    -> publish live results to the local processed store (and later Supabase).

For the no-40GB-dataset scaffold this ingests from the *synthetic* generator so
you can demo live monitoring without real feeds. To swap in real AIS/SAR, replace
`ingest()` with a real poller (MarineCadastre download / Zenodo SAR fetch).

Usage:
    python scripts/monitor_service.py            # start and run forever
    python scripts/monitor_service.py --once     # single pass, for tests
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from app.attribution.service import AttributionService  # noqa: E402
from app.config import settings  # noqa: E402
from app.core.utils import utcnow  # noqa: E402
from generate_demo_data import build_slicks, build_tracks  # noqa: E402

POLL_INTERVAL_SEC = 60


class LiveStateStore:
    """Publishes the current live state to data/processed/live_state.json.

    The dashboard reads this file (or the API serves it) to render active spills
    and their attribution cards in near-real-time.
    """

    LOG = settings.DATA_PROCESSED_DIR / "live_state.json"
    LOG.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, slicks: list, reports: list, events: list) -> None:
        state = {
            "updated_at": utcnow().isoformat(),
            "active_spills": [s.model_dump(mode="json") for s in slicks],
            "attribution": [r.model_dump(mode="json") for r in reports],
            "recent_events": events[-20:],  # keep last 20 alerts
        }
        self.LOG.write_text(json.dumps(state, indent=2))


def run_once() -> dict:
    """One full pipeline pass. Returns summary counts for tests/logging."""
    slicks = build_slicks()
    tracks = build_tracks()
    service = AttributionService()
    reports = [service.attribute(s, tracks) for s in slicks]
    store = LiveStateStore()

    # Emit an alert event for each newly-attributed spill (dedupe by slick id).
    from app.core.utils import gen_id
    events = [
        {
            "id": gen_id("evt"),
            "time": utcnow().isoformat(),
            "slick_id": r.slick_id,
            "message": (
                f"ALERT Spill {r.slick_id} -> suspected vessel "
                f"{r.top_suspect.vessel_name or r.top_suspect.mmsi} "
                f"({r.top_suspect.correlation_score*100:.0f}%)"
                if r.top_suspect
                else f"Spill {r.slick_id} - no suspect in window"
            ),
        }
        for r in reports
    ]

    store.publish(slicks, reports, events)
    return {"slicks": len(slicks), "reports": len(reports), "events": len(events)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Oil spill real-time monitor")
    parser.add_argument("--once", action="store_true", help="run a single pass")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL_SEC,
                        help="poll interval in seconds")
    args = parser.parse_args()

    print("== Marine Oil Spill Monitoring Service ==")
    print(f"   live state -> {LiveStateStore.LOG}")
    if args.once:
        summary = run_once()
        print("   one-time pass:", summary)
        return

    print(f"   polling every {args.interval}s (Ctrl+C to stop)")
    while True:
        try:
            summary = run_once()
            print(f"   [{utcnow().isoformat()}] pass -> {summary}")
        except Exception as exc:  # keep the monitor alive on transient errors
            print(f"   [{utcnow().isoformat()}] ERROR {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
