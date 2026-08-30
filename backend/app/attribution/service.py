"""Phase 3: vessel attribution via spatiotemporal correlation.

Given a detected slick (geometry + detection time) and a set of cleaned vessel
tracks, this stage computes a per-vessel composite score and returns a ranked
suspect list with confidence.

Scoring factors (weighted fusion):
    - proximity  : spatial closeness to the slick centroid
    - trajectory : temporal/location consistency with the slick's presence
    - behavior   : anomalous navigation (sudden stop/drift) - discharge signature
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from app.config import settings
from app.core.schemas import (
    AisMessage,
    AttributionReport,
    AttributionScore,
    SlickDetection,
    VesselTrack,
)
from app.core.utils import haversine_km, utcnow


class AttributionService:
    """Ranks suspect vessels for each detected slick."""

    def __init__(self, search_radius_km: float | None = None,
                 window_hours: float | None = None) -> None:
        self.radius_km = search_radius_km or settings.ATTRIBUTION_SEARCH_RADIUS_KM
        self.window_hours = window_hours or settings.ATTRIBUTION_WINDOW_HOURS

    def attribute(
        self,
        slick: SlickDetection,
        tracks: Iterable[VesselTrack],
    ) -> AttributionReport:
        """Attribute a slick to the vessels that best explain its presence."""
        scores: list[AttributionScore] = []
        for track in tracks:
            if track.trust_score < settings.AIS_SPOOF_SCORE_THRESHOLD:
                # Drop vessels we cannot trust (spoofed/flaky AIS).
                continue

            proximity = self._proximity_score(slick, track)
            if proximity < 0.05:
                continue  # vessel too far away to be a candidate

            behavior = self._behavior_score(track)
            trajectory = self._trajectory_score(slick, track)

            overall = 0.5 * proximity + 0.3 * trajectory + 0.2 * behavior
            scores.append(
                AttributionScore(
                    mmsi=track.mmsi,
                    vessel_class=track.vessel_class,
                    proximity_score=proximity,
                    trajectory_score=trajectory,
                    behavior_score=behavior,
                    overall_confidence=round(overall, 3),
                    evidence={"consistent_points": self._count_near(slick, track)},
                )
            )

        scores.sort(key=lambda s: s.overall_confidence, reverse=True)
        top = scores[0] if scores else None
        return AttributionReport(
            slick_id=slick.id,
            generated_at=utcnow(),
            suspect_vessels=scores,
            top_suspect=top,
        )

    # -- scoring internals -------------------------------------------------- #

    @staticmethod
    def _proximity_score(slick: SlickDetection, track: VesselTrack) -> float:
        if not track.points:
            return 0.0
        g = slick.geometry
        dists = [
            haversine_km(g.centroid_lat, g.centroid_lon, p.lat, p.lon)
            for p in track.points
        ]
        min_dist = min(dists)
        # Fall off linearly from 1.0 at 0 km to ~0.1 at radius.
        return max(0.0, 1.0 - min_dist / 50.0)

    @staticmethod
    def _trajectory_score(slick: SlickDetection, track: VesselTrack) -> float:
        """Fraction of vessel points temporally within the slick window AND close."""
        return AttributionService._count_near(slick, track) / max(1, len(track.points))

    @staticmethod
    def _count_near(slick: SlickDetection, track: VesselTrack) -> int:
        g = slick.geometry
        window_start = slick.detected_at - timedelta(hours=settings.ATTRIBUTION_WINDOW_HOURS)
        window_end = slick.detected_at + timedelta(hours=settings.ATTRIBUTION_WINDOW_HOURS)
        return sum(
            1
            for p in track.points
            if window_start <= p.timestamp <= window_end
            and haversine_km(g.centroid_lat, g.centroid_lon, p.lat, p.lon) <= 50.0
        )

    @staticmethod
    def _behavior_score(track: VesselTrack) -> float:
        """Reward vessels whose speed profile suggests a discharge stop/lingering."""
        if len(track.points) < 2:
            return 0.5
        speeds = [p.sog_knots for p in track.points]
        avg = sum(speeds) / len(speeds)
        # A vessel idling near the spill (low average speed) is more suspect.
        return float(max(0.0, 1.0 - avg / 10.0))
