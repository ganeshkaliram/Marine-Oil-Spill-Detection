from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ais.service import AisAnomalyDetector, AisProcessingService
from app.attribution.service import AttributionService
from app.core.schemas import (
    AisMessage,
    AisVesselClass,
    SlickDetection,
    SlickGeometry,
    VesselTrack,
)
from app.core.utils import gen_id


def _msg(mmsi, lat, lon, ts, sog=10.0, cog=90.0, cls=AisVesselClass.TANKER):
    return AisMessage(
        mmsi=mmsi,
        timestamp=ts,
        lat=lat,
        lon=lon,
        sog_knots=sog,
        cog_deg=cog,
        vessel_class=cls,
    )


T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


class TestAisAnomaly:
    def test_impossible_speed_flagged(self):
        fast = [
            _msg(1, 10.0, 10.0, T0),
            _msg(1, 10.0, 11.0, T0 + timedelta(minutes=1)),  # ~60km in 1min
        ]
        det = AisAnomalyDetector()
        anomalies = det.scan(fast)
        assert any(a.anomaly_type == "impossible_speed" for a in anomalies)

    def test_clean_stream_no_anomalies(self):
        clean = [
            _msg(2, 10.0, 10.0, T0, sog=10),
            _msg(2, 10.001, 10.001, T0 + timedelta(minutes=10), sog=10),
        ]
        det = AisAnomalyDetector()
        assert det.scan(clean) == []


class TestAisProcessing:
    def test_tracks_grouped_and_trusted(self):
        svc = AisProcessingService()
        messages = [_msg(9, 10.0, 10.0, T0), _msg(8, 20.0, 20.0, T0)]
        tracks = svc.build_tracks(messages)
        assert len(tracks) == 2
        assert {t.mmsi for t in tracks} == {8, 9}
        assert all(t.trust_score == 1.0 for t in tracks)


class TestAttribution:
    def _make_slick(self, lat=10.0, lon=10.0):
        return SlickDetection(
            id=gen_id("slick"),
            scene_id="S1A_test",
            detected_at=T0,
            source_sensor="sentinel-1",
            polarization="VV+VH",
            geometry=SlickGeometry(
                centroid_lat=lat,
                centroid_lon=lon,
                area_m2=1e6,
                perimeter_m=4e3,
                bbox_px=(0, 0, 10, 10),
            ),
            confidence=0.95,
        )

    def test_suspects_ranked_by_proximity(self):
        slick = self._make_slick()
        near = VesselTrack(
            mmsi=1, vessel_class=AisVesselClass.TANKER,
            points=[_msg(1, 10.001, 10.001, T0, sog=2.0)], trust_score=1.0,
        )
        far = VesselTrack(
            mmsi=2, vessel_class=AisVesselClass.CARGO,
            points=[_msg(2, 45.0, 45.0, T0, sog=14.0)], trust_score=1.0,
        )
        report = AttributionService().attribute(slick, [near, far])
        assert report.top_suspect is not None
        assert report.top_suspect.mmsi == 1  # near vessel wins

    def test_correlation_card_fields(self):
        """Output matches the human-facing correlation card format."""
        slick = self._make_slick(lat=10.0, lon=10.0)
        near = VesselTrack(
            mmsi=1, vessel_class=AisVesselClass.TANKER,
            points=[_msg(1, 10.002, 10.002, T0, sog=2.0)], trust_score=1.0,
        )
        report = AttributionService().attribute(slick, [near])
        s = report.top_suspect
        assert s is not None
        assert 0.0 <= s.correlation_score <= 1.0
        # ~0.3 km away -> distance small, intersection True
        assert s.distance_from_spill_km < 1.0
        assert s.track_intersection is True
        assert s.vessel_speed_knots == 2.0
        assert s.vessel_class == AisVesselClass.TANKER

    def test_spoofed_track_excluded(self):
        slick = self._make_slick()
        untrusted = VesselTrack(
            mmsi=3, vessel_class=AisVesselClass.TANKER,
            points=[_msg(3, 10.001, 10.001, T0, sog=2.0)], trust_score=0.1,
        )
        report = AttributionService().attribute(slick, [untrusted])
        assert report.suspect_vessels == []
        assert report.top_suspect is None
