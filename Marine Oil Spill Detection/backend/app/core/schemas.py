"""Domain data models shared across the pipeline.

These Pydantic models define the contracts between detection, AIS analysis,
and attribution stages. They are intentionally storage-agnostic so future DB
backends can be swapped in without changing the API layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Phase 1: Detection
# --------------------------------------------------------------------------- #


class SlickGeometry(BaseModel):
    """Geometric properties of a detected slick."""

    centroid_lat: float
    centroid_lon: float
    area_m2: float
    perimeter_m: float
    bbox_px: tuple[int, int, int, int]  # (xmin, ymin, xmax, ymax)
    pixel_coords: list[tuple[float, float]] = Field(default_factory=list)


class SlickDetection(BaseModel):
    """A single detected oil slick with characterization metadata."""

    id: str
    scene_id: str                       # source SAR granule id
    detected_at: datetime
    source_sensor: Literal["sentinel-1", "sentinel-2", "planetscope"]
    polarization: str | None = None     # e.g. "VV", "VH", "VV+VH"
    geometry: SlickGeometry
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_age_hours: float | None = None
    weathering: str | None = None       # e.g. "fresh", "moderate", "weathered"
    oil_type: str | None = None         # from histogram/spectral analysis of spill pixels
    model_meta: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Phase 2: AIS
# --------------------------------------------------------------------------- #


class AisVesselClass(str, Enum):
    TANKER = "tanker"
    CARGO = "cargo"
    FISHING = "fishing"
    PASSENGER = "passenger"
    OTHER = "other"


class AisMessage(BaseModel):
    """A single clean, validated AIS position report."""

    mmsi: int
    timestamp: datetime
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    sog_knots: float
    cog_deg: float
    vessel_class: AisVesselClass | None = None


class AisAnomaly(BaseModel):
    """An anomaly flagged on a vessel's AIS stream."""

    mmsi: int
    timestamp: datetime
    anomaly_type: Literal[
        "position_jump",
        "impossible_speed",
        "signal_gap",
        "spoofed_signal",
    ]
    severity: float = Field(ge=0.0, le=1.0)
    details: dict = Field(default_factory=dict)


class VesselTrack(BaseModel):
    """Smoothed trajectory of a vessel after anomaly filtering."""

    mmsi: int
    vessel_name: str | None = None
    vessel_class: AisVesselClass | None = None
    points: list[AisMessage]
    trust_score: float = Field(ge=0.0, le=1.0)  # 1.0 = fully trusted
    anomalies: list[AisAnomaly] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Phase 3: Attribution
# --------------------------------------------------------------------------- #


class AttributionScore(BaseModel):
    """Composite score attributing a slick to a single vessel.

    Mirrors the human-facing correlation card:
        Likely vessel / Correlation score / Distance from spill / Track intersection
    """

    mmsi: int
    vessel_name: str | None = None
    vessel_class: AisVesselClass | None = None
    vessel_cargo: str | None = None        # e.g. "crude oil", "chemical X"

    # Correlation card fields
    correlation_score: float = Field(ge=0.0, le=1.0)   # 0..1 -> 87%
    distance_from_spill_km: float = Field(ge=0.0)       # e.g. 2.4
    track_intersection: bool = False                    # route intersects spill
    vessel_speed_knots: float = Field(default=0.0, ge=0.0)
    vessel_direction_deg: float = Field(default=0.0, ge=0.0, le=360.0)

    # Keep detailed scoring signals (computed independently)
    proximity_score: float = Field(ge=0.0, le=1.0)
    trajectory_score: float = Field(ge=0.0, le=1.0)
    behavior_score: float = Field(ge=0.0, le=1.0)
    evidence: dict = Field(default_factory=dict)


class AttributionReport(BaseModel):
    """Final result linking a slick to ranked suspect vessels."""

    slick_id: str
    generated_at: datetime
    origin_candidates: list[dict] = Field(default_factory=list)  # hindcast PGF
    suspect_vessels: list[AttributionScore]
    top_suspect: AttributionScore | None = None
