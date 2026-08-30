"""Generate synthetic demo data so the pipeline is runnable without real
satellite/AIS feeds.

Produces:
    - data/processed/demo_slicks.json     : current/live slick detections (with oil type)
    - data/processed/demo_tracks.json     : vessel tracks incl. a "suspect" tanker
    - data/processed/demo_reports.json    : attribution reports (correlation cards)
    - data/processed/historical_spills.json : pre-existing spills for the dashboard

The synthetic scenario models a *deliberate discharge*: a tanker slows to near
zero speed (discharge signature) adjacent to the slick, giving the attribution
service an unambiguous top suspect to demonstrate the full pipeline.
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


def _geom(lat, lon, area_m2=2.5e6):
    return SlickGeometry(
        centroid_lat=lat, centroid_lon=lon,
        area_m2=area_m2, perimeter_m=9e3,
        bbox_px=(100, 100, 300, 250),
    )


def build_slicks() -> list[SlickDetection]:
    """One live spill (detected 2h ago) + indicate it's the active event."""
    t0 = utcnow() - timedelta(hours=2)
    return [
        SlickDetection(
            id=gen_id("slick"), scene_id="S1A_live",
            detected_at=t0, source_sensor="sentinel-1",
            polarization="VV+VH", geometry=_geom(10.5, 10.5),
            confidence=0.93, estimated_age_hours=4.0, weathering="moderate",
            oil_type="crude-oil",
            model_meta={"histogram_bin": "thick/emulsion", "feed_source": "simulated"},
        )
    ]


def build_tracks() -> list[VesselTrack]:
    """Tanker decelerates and lingers near the spill (discharge signature).

    Includes static voyage data (destination, ETA, cargo type) that commodity
    traders need for analysis.
    """
    t0 = utcnow() - timedelta(hours=2)
    pts = [
        AisMessage(mmsi=413000111, timestamp=t0 + timedelta(minutes=-40),
                   lat=10.53, lon=10.52, sog_knots=12.0, cog_deg=185,
                   vessel_class=AisVesselClass.TANKER,
                   vessel_name="MT SUSPECT-ONE", destination="SGSIN",
                   eta=t0 + timedelta(hours=6), cargo_type="crude-oil",
                   draft_dm=12.5, ship_length_m=183, ship_breadth_m=32),
        AisMessage(mmsi=413000111, timestamp=t0 + timedelta(minutes=-25),
                   lat=10.50, lon=10.51, sog_knots=5.0, cog_deg=175,
                   vessel_class=AisVesselClass.TANKER,
                   vessel_name="MT SUSPECT-ONE", destination="SGSIN",
                   cargo_type="crude-oil"),
        AisMessage(mmsi=413000111, timestamp=t0 + timedelta(minutes=-10),
                   lat=10.49, lon=10.50, sog_knots=1.2, cog_deg=165,
                   vessel_class=AisVesselClass.TANKER,
                   vessel_name="MT SUSPECT-ONE", destination="SGSIN",
                   cargo_type="crude-oil"),
        AisMessage(mmsi=413000111, timestamp=t0, lat=10.50, lon=10.49,
                   sog_knots=0.8, cog_deg=160, vessel_class=AisVesselClass.TANKER,
                   vessel_name="MT SUSPECT-ONE", destination="SGSIN",
                   cargo_type="crude-oil"),
    ]
    # A distant innocent cargo vessel (far away, high speed).
    far = AisMessage(mmsi=636000222, timestamp=t0, lat=30.0, lon=-70.0,
                     sog_knots=15.0, cog_deg=90, vessel_class=AisVesselClass.CARGO,
                     vessel_name="MV INNOCENT", destination="AEJEA",
                     cargo_type="general-cargo", ship_length_m=225)
    return [
        VesselTrack(
            mmsi=413000111, vessel_name="MT SUSPECT-ONE",
            vessel_class=AisVesselClass.TANKER, points=pts,
            trust_score=1.0, anomalies=[],
            destination="SGSIN", eta=t0 + timedelta(hours=6),
            cargo_type="crude-oil", draft_dm=12.5,
            ship_length_m=183, ship_breadth_m=32,
        ),
        VesselTrack(
            mmsi=636000222, vessel_name="MV INNOCENT",
            vessel_class=AisVesselClass.CARGO, points=[far],
            trust_score=1.0, anomalies=[],
            destination="AEJEA", cargo_type="general-cargo",
            ship_length_m=225,
        ),
    ]


def build_historical_spills() -> list[dict]:
    """Pre-existing spills shown on the dashboard as historical context."""
    base = utcnow()
    return [
        {
            "id": "hist_001",
            "centroid": {"lat": 12.8, "lon": 44.3},       # Gulf of Aden
            "area_m2": 5.1e6,
            "oil_type": "heavy-fuel-oil",
            "status": "historical",
            "detected_at": (base - timedelta(days=12)).isoformat(),
        },
        {
            "id": "hist_002",
            "centroid": {"lat": -1.9, "lon": 104.8},      # near Singapore Strait
            "area_m2": 3.4e6,
            "oil_type": "light-diesel",
            "status": "historical",
            "detected_at": (base - timedelta(days=40)).isoformat(),
        },
    ]


def main() -> None:
    slicks = build_slicks()
    tracks = build_tracks()
    historical = build_historical_spills()

    out = {
        "generated_at": utcnow().isoformat(),
        "slicks": [], "tracks": [], "reports": [], "historical": historical,
    }
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
    (processed / "demo_slicks.json").write_text(json.dumps(out["slicks"], indent=2))
    (processed / "demo_tracks.json").write_text(json.dumps(out["tracks"], indent=2))
    (processed / "demo_reports.json").write_text(json.dumps(out["reports"], indent=2))
    (processed / "demo_historical.json").write_text(json.dumps(historical, indent=2))

    # Write vessel static data (for trader-critical fields)
    vessels = [
        {
            "mmsi": t["mmsi"],
            "vessel_name": t["vessel_name"],
            "vessel_class": t["vessel_class"],
            "destination": t.get("destination"),
            "eta": t.get("eta"),
            "cargo_type": t.get("cargo_type"),
            "draft_dm": t.get("draft_dm"),
            "ship_length_m": t.get("ship_length_m"),
            "ship_breadth_m": t.get("ship_breadth_m"),
            "trust_score": t["trust_score"],
        }
        for t in out["tracks"]
    ]
    (processed / "demo_vessels.json").write_text(json.dumps(vessels, indent=2))

    # Initialize database with demo data
    from app.core.db import get_db
    db = get_db()
    for vessel in vessels:
        from app.core.schemas import AisStaticData, AisVesselClass
        vc = AisVesselClass(vessel["vessel_class"]) if vessel["vessel_class"] in [e.value for e in AisVesselClass] else None
        db.upsert_vessel(AisStaticData(
            mmsi=vessel["mmsi"],
            vessel_name=vessel["vessel_name"],
            vessel_class=vc,
            cargo_type=vessel.get("cargo_type"),
            destination=vessel.get("destination"),
            eta=vessel.get("eta"),
            draft_dm=vessel.get("draft_dm"),
            ship_length_m=vessel.get("ship_length_m"),
            ship_breadth_m=vessel.get("ship_breadth_m"),
        ))

    print("Wrote demo data to", processed)
    print("Database initialized at", processed / "maritime.db")

    rep = out["reports"][0]
    top = rep["top_suspect"]
    print("\n=== CORRELATION CARD ===")
    print(f"Likely vessel:      {top['vessel_name']} (MMSI {top['mmsi']})")
    print(f"Vessel type:        {top['vessel_class']}")
    print(f"Correlation score:  {top['correlation_score']*100:.0f}%")
    print(f"Distance from spill {top['distance_from_spill_km']} km")
    print(f"Track intersection: {top['track_intersection']}")
    print(f"Vessel speed:       {top['vessel_speed_knots']} kn (near-0 = discharge)")
    print(f"Vessel direction:   {top['vessel_direction_deg']} deg")
    print(f"Oil type:           {out['slicks'][0]['oil_type']}")


if __name__ == "__main__":
    main()
