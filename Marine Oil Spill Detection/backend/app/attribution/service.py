"""Phase 3: vessel attribution via spatiotemporal correlation.

Given a detected slick (geometry + detection time) and a set of cleaned vessel
tracks, produce a human-facing **correlation card** for each candidate:

    Likely vessel / Correlation score / Distance from spill / Track intersection
    Vessel speed & direction / Oil type

Scoring factors (weighted fusion):
    - proximity  : haversine distance from the vessel to the slick centroid
    - trajectory : temporal/location consistency with the slick's presence
    - behavior   : anomalous navigation (near-zero speed = discharge signature)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from app.config import settings
from app.core.schemas import (
    AttributionReport,
    AttributionScore,
    SlickDetection,
    VesselTrack,
)
from app.core.utils import haversine_km, utcnow

# Relative weights of each factor in the final correlation score.
_W_PROXIMITY = 0.5
_W_TRAJECTORY = 0.3
_W_BEHAVIOR = 0.2


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
        g = slick.geometry

        for track in tracks:
            if track.trust_score < settings.AIS_SPOOF_SCORE_THRESHOLD:
                # Drop vessels we cannot trust (spoofed/flaky AIS).
                continue

            proximity = self._proximity_score(slick, track)
            if proximity < 0.05:
                continue  # too far to be a candidate

            min_dist_km = self._min_distance_km(slick, track)
            trajectory = self._trajectory_score(slick, track)
            behavior = self._behavior_score(track)
            correlation = (
                _W_PROXIMITY * proximity
                + _W_TRAJECTORY * trajectory
                + _W_BEHAVIOR * behavior
            )

            # Nearest-point vessel speed/direction snapshot (from earliest point
            # inside the slick window).
            speed, direction = self._vessel_state(track)

            scores.append(
                AttributionScore(
                    mmsi=track.mmsi,
                    vessel_class=track.vessel_class,
                    vessel_name=self._vessel_name(track),
                    correlation_score=round(correlation, 3),
                    distance_from_spill_km=round(min_dist_km, 2),
                    track_intersection=min_dist_km <= self.radius_km,
                    vessel_speed_knots=round(speed, 2),
                    vessel_direction_deg=round(direction, 1),
                    proximity_score=proximity,
                    trajectory_score=trajectory,
                    behavior_score=behavior,
                    evidence={
                        "trust_score": track.trust_score,
                        "anomaly_count": len(track.anomalies),
                        "consistent_points": self._count_near(slick, track),
                    },
                )
            )

        scores.sort(key=lambda s: s.correlation_score, reverse=True)
        top = scores[0] if scores else None
        return AttributionReport(
            slick_id=slick.id,
            generated_at=utcnow(),
            suspect_vessels=scores,
            top_suspect=top,
        )

    # -- scoring internals -------------------------------------------------- #

    def _min_distance_km(self, slick: SlickDetection, track: VesselTrack) -> float:
        """Closest approach distance (km) between any vessel point and the slick."""
        if not track.points:
            return float("inf")
        g = slick.geometry
        return min(
            haversine_km(g.centroid_lat, g.centroid_lon, p.lat, p.lon)
            for p in track.points
        )

    def _proximity_score(self, slick: SlickDetection, track: VesselTrack) -> float:
        """1.0 at 0 km falling linearly to ~0.1 at 50 km."""
        d = self._min_distance_km(slick, track)
        if d == float("inf"):
            return 0.0
        return max(0.0, min(1.0, 1.0 - d / 50.0))

    def _trajectory_score(self, slick, track) -> float:
        """Fraction of vessel points within the slick time window AND spatially close."""
        return self._count_near(slick, track) / max(1, len(track.points))

    def _count_near(self, slick: SlickDetection, track: VesselTrack) -> int:
        g = slick.geometry
        window_start = slick.detected_at - timedelta(hours=self.window_hours)
        window_end = slick.detected_at + timedelta(hours=self.window_hours)
        return sum(
            1
            for p in track.points
            if window_start <= p.timestamp <= window_end
            and haversine_km(g.centroid_lat, g.centroid_lon, p.lat, p.lon) <= 50.0
        )

    def _behavior_score(self, track: VesselTrack) -> float:
        """Reward vessels whose speed profile suggests a discharge stop/lingering."""
        if len(track.points) < 2:
            return 0.5
        avg = sum(p.sog_knots for p in track.points) / len(track.points)
        # A vessel idling near the spill (low average speed) is more suspect.
        return float(max(0.0, min(1.0, 1.0 - avg / 10.0)))

    @staticmethod
    def _vessel_state(track: VesselTrack) -> tuple[float, float]:
        """Return (sog, cog) from the most recent point, or (0.0, 0.0)."""
        if not track.points:
            return 0.0, 0.0
        p = max(track.points, key=lambda x: x.timestamp)
        return p.sog_knots, p.cog_deg

    @staticmethod
    def _vessel_name(track: VesselTrack) -> str | None:
        return track.vessel_name
