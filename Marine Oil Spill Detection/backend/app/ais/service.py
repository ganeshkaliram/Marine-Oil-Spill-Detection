"""Phase 2 service: AIS ingestion, anomaly detection, and clean-track building.

Two responsibilities:
1. Structural anomaly detection (position jumps, impossible speed, signal gaps,
   spoof detection) that filters *untrustworthy* AIS before it is used.
2. Aggregation of clean messages into per-vessel smoothed tracks with a trust
   score, so attribution only sees validated data.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from app.config import settings
from app.core.schemas import AisAnomaly, AisMessage, VesselTrack
from app.core.utils import haversine_km


class AisAnomalyDetector:
    """Detects spoofing and data-quality anomalies in raw AIS streams."""

    def __init__(self) -> None:
        self.max_speed = settings.AIS_MAX_SPEED_KNOTS
        self.max_jump_km = settings.AIS_MAX_POSITION_JUMP_KM

    def scan(self, messages: Iterable[AisMessage]) -> list[AisAnomaly]:
        """Flag anomalies across a time-ordered series of messages for one vessel."""
        anomalies: list[AisAnomaly] = []
        ordered = sorted(messages, key=lambda m: m.timestamp)
        prev: AisMessage | None = None

        for msg in ordered:
            if prev is not None:
                dt_h = (msg.timestamp - prev.timestamp).total_seconds() / 3600.0

                # Impossible speed (displacement time).
                dist_km = haversine_km(prev.lat, prev.lon, msg.lat, msg.lon)
                implied_knots = (dist_km / dt_h) * 0.539957 if dt_h > 0 else 0.0
                if implied_knots > self.max_speed:
                    anomalies.append(
                        AisAnomaly(
                            mmsi=msg.mmsi,
                            timestamp=msg.timestamp,
                            anomaly_type="impossible_speed",
                            severity=min(1.0, implied_knots / self.max_speed),
                            details={"implied_knots": round(implied_knots, 1)},
                        )
                    )

                # Position jump between messages.
                if dist_km > self.max_jump_km:
                    anomalies.append(
                        AisAnomaly(
                            mmsi=msg.mmsi,
                            timestamp=msg.timestamp,
                            anomaly_type="position_jump",
                            severity=min(1.0, dist_km / (self.max_jump_km * 2)),
                            details={"jump_km": round(dist_km, 1)},
                        )
                    )

                # Signal gap (suspicious silence > threshold).
                gap_hours = (msg.timestamp - prev.timestamp).total_seconds() / 3600.0
                if gap_hours > settings.ATTRIBUTION_WINDOW_HOURS:
                    anomalies.append(
                        AisAnomaly(
                            mmsi=msg.mmsi,
                            timestamp=msg.timestamp,
                            anomaly_type="signal_gap",
                            severity=min(1.0, gap_hours / 24.0),
                            details={"gap_hours": round(gap_hours, 1)},
                        )
                    )
            prev = msg
        return anomalies

    def trust_score(self, anomalies: list[AisAnomaly]) -> float:
        """Convert a list of anomalies into a 0..1 trust score (1 = fully trusted)."""
        if not anomalies:
            return 1.0
        severity = sum(a.severity for a in anomalies) / float(len(anomalies))
        # Spoofing is treated much more harshly.
        spoof = any(a.anomaly_type == "spoofed_signal" for a in anomalies)
        score = 1.0 - (0.5 * severity + 0.5 * int(spoof))
        return max(0.0, min(1.0, score))


class AisProcessingService:
    """Builds clean vessel tracks from "raw" messages."""

    def __init__(self, detector: AisAnomalyDetector | None = None) -> None:
        self.detector = detector or AisAnomalyDetector()

    def build_tracks(self, messages: Iterable[AisMessage]) -> list[VesselTrack]:
        """Group validated messages by MMSI into tracks with trust scores."""
        by_mmsi: dict[int, list[AisMessage]] = {}
        for m in messages:
            by_mmsi.setdefault(m.mmsi, []).append(m)

        tracks: list[VesselTrack] = []
        for mmsi, msgs in by_mmsi.items():
            anomalies = self.detector.scan(msgs)
            trusted = [m for m in msgs if not self._is_spoofed(m, anomalies)]
            tracks.append(
                VesselTrack(
                    mmsi=mmsi,
                    vessel_class=msgs[0].vessel_class,
                    points=trusted,
                    trust_score=self.detector.trust_score(anomalies),
                    anomalies=anomalies,
                )
            )
        return tracks

    @staticmethod
    def _is_spoofed(m: AisMessage, anomalies: list[AisAnomaly]) -> bool:
        return any(
            a.anomaly_type == "spoofed_signal"
            and abs((a.timestamp - m.timestamp).total_seconds()) < 60
            for a in anomalies
        )
