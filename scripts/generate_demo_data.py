"""Generate synthetic demo data so the pipeline is runnable without real
satellite/AIS feeds.

Produces:
    - data/processed/demo_slicks.json  : a few fabricated SlickDetections
    - data/processed/demo_tracks.json  : fabricated VesselTracks incl. a "suspect"

This lets you exercise Phase 3 (attribution) and the dashboard end-to-end while
Phase 1 model training is still in progress.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.attribution.service import AttributionService
from app.core.schemas import (
    AisMessage,
    AisVesselClass,
    SlickDetection,
    SlickGeometry,
    VesselTrack,
)
from app.core.utils import gen_id, utcnow


def _geom(lat, lon):
    return SlickGeometry(
        centroid_lat=lat, centroid_lon=lon,
        area_m2=2.5e6, perimeter_m=9e3,
        bbox_px=(100, 100, 300, 250),
    )


def build_slicks() -> list[SlickDetection]:
    t0 = utcnow() - timedelta(hours=2)
    return [
        SlickDetection(
            id=gen_id("slick"), scene_id="S1A_demo",
            detected_at=t0, source_sensor="sentinel-1",
            polarization="VV+VH", geometry=_geom(10.5, 10.5),
            confidence=0.93, estimated_age_hours=4.0, weathering="moderate",
        )
    ]


def build_tracks() -> list[VesselTrack]:
    t0 = utcnow() - timedelta(hours=2)
    pts = [
        AisMessage(mmsi=413000111, timestamp=t0 + timedelta(minutes=-40),
                   lat=10.52, lon=10.52, sog_knots=1.5, cog_deg=200,
                   vessel_class=AisVesselClass.TANKER),
        AisMessage(mmsi=413000111, timestamp=t0 + timedelta(minutes=-20),
                   lat=10.49, lon=10.51, sog_knots=2.0, cog_deg=180,
                   vessel_class=AisVesselClass.TANKER),
        AisMessage(mmsi=413000111, timestamp=t0, lat=10.51, lon=10.49,
                   sog_knots=3.0, cog_deg=150, vessel_class=AisVesselClass.TANKER),
    ]
    # A distant innocent cargo vessel.
    far = AisMessage(mmsi=636000222, timestamp=t0, lat=30.0, lon=-70.0,
                     sog_knots=15.0, cog_deg=90, vessel_class=AisVesselClass.CARGO)
    return [
        VesselTrack(mmsi=413000111, vessel_class=AisVesselClass.TANKER,
                    points=pts, trust_score=1.0, anomalies=[]),
        VesselTrack(mmsi=636000222, vessel_class=AisVesselClass.CARGO,
                    points=[far], trust_score=1.0, anomalies=[]),
    ]


def main() -> None:
    slicks = build_slicks()
    tracks = build_tracks()

    out = {"generated_at": utcnow().isoformat(), "slicks": [], "tracks": [], "reports": []}
    service = AttributionService()
    for s in slicks:
        out["slicks"].append(s.model_dump(mode="json"))
        rep = service.attribute(s, tracks)
        out["reports"].append(rep.model_dump(mode="json"))
    for t in tracks:
        out["tracks"].append(t.model_dump(mode="json"))

    from app.config import settings
    processed = settings.DATA_PROCESSED_DIR
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "demo_slicks.json").write_text(
        json.dumps(out["slicks"], indent=2))
    (processed / "demo_tracks.json").write_text(
        json.dumps(out["tracks"], indent=2))
    (processed / "demo_reports.json").write_text(
        json.dumps(out["reports"], indent=2))
    print("Wrote demo data to", processed)
    print("Top suspect:", out["reports"][0]["top_suspect"])


if __name__ == "__main__":
    main()
