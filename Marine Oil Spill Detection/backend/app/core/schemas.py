"""Domain data models shared across the pipeline.

These Pydantic models define the contracts between detection, AIS analysis,
and attribution stages. They are intentionally storage-agnostic so future DB
backends can be swapped in without changing the API layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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


class AisStaticData(BaseModel):
    """Static voyage data from AIS Message Types 5 and 24.

    Contains vessel identification, cargo, and voyage planning info that
    commodity traders rely on for ETA analysis, route monitoring, and
    cargo tracking.
    """

    mmsi: int
    vessel_name: str | None = None
    callsign: str | None = None
    imo: int | None = None
    ship_type: int | None = None         # AIS ship type code (30-39= cargo, 80-89= tanker, etc.)
    vessel_class: AisVesselClass | None = None  # derived from ship_type
    cargo_type: str | None = None        # human-readable: "crude-oil", "lng", "chemical", etc.
    destination: str | None = None       # UN/LOCODE, e.g. "SGSIN"
    eta: datetime | None = None          # estimated time of arrival at destination
    draft_dm: float | None = None        # present draft in decimetres
    ship_length_m: float | None = None
    ship_breadth_m: float | None = None
    ship_type_cargo: str | None = None   # detailed cargo description from AIVDM Type 8 (if available)
    dte: bool | None = None              # data terminal equipment ready
    received_at: datetime | None = None

    @field_validator("eta", mode="before")
    @classmethod
    def _coerce_eta(cls, v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return None
        return v


# AIS ship type code ranges -> human-readable categories
_SHIP_TYPE_RANGES = {
    (30, 39): "cargo",
    (40, 49): "hazardous-a",
    (50, 59): "hazardous-b",
    (60, 69): "hazardous-c",
    (70, 79): "hazardous-d",
    (80, 89): "tanker",
    (90, 99): "other",
}

# Cargo type codes for hazardous-b category (chemical tankers)
_CARGO_TYPE_CODES_B = {
    0: None, 1: "chemical-a", 2: "chemical-b", 3: "chemical-c",
    4: "chemical-d", 5: "chemical-e", 6: "chemical-f",
    7: "chemical-g", 8: "chemical-h", 9: "chemical-i",
    10: "chemical-j", 11: "chemical-k", 12: "chemical-l",
    13: "chemical-m", 14: "chemical-n", 15: "chemical-o",
    16: "chemical-p", 17: "chemical-q", 18: "chemical-r",
    19: "chemical-s", 20: "chemical-t", 21: "chemical-u",
    22: "chemical-v", 23: "chemical-w", 24: "chemical-x",
    25: "chemical-y", 26: "chemical-z",
    27: "liquid-other",
}

# Cargo type codes for tanker category
_CARGO_TYPE_CODES_TANKER = {
    0: None, 1: "oil", 2: "lng", 3: "lpg", 4: "chemical",
    5: "oil-imo-ii", 6: "oil-imo-iii", 7: "chemical-imo-ii",
    8: "chemical-imo-iii", 9: "liquid-other",
}


def ship_type_to_class(code: int | None) -> AisVesselClass | None:
    """Map AIS ship type code to our vessel class enum."""
    if code is None:
        return None
    if 80 <= code <= 89:
        return AisVesselClass.TANKER
    if 30 <= code <= 39:
        return AisVesselClass.CARGO
    if 70 <= code <= 79:
        return AisVesselClass.FISHING
    if 60 <= code <= 69:
        return AisVesselClass.PASSENGER
    return AisVesselClass.OTHER


def cargo_type_from_codes(ship_type: int | None, cargo_code: int | None) -> str | None:
    """Map AIS ship type + cargo type code to a human-readable cargo description."""
    if ship_type is None or cargo_code is None:
        return None
    if 80 <= ship_type <= 89:
        return _CARGO_TYPE_CODES_TANKER.get(cargo_code)
    if 50 <= ship_type <= 59:
        return _CARGO_TYPE_CODES_B.get(cargo_code)
    return None


class AisMessage(BaseModel):
    """A single clean, validated AIS position report."""

    mmsi: int
    timestamp: datetime
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    sog_knots: float
    cog_deg: float
    vessel_class: AisVesselClass | None = None
    # Extended fields from static data (populated when available)
    vessel_name: str | None = None
    destination: str | None = None
    eta: datetime | None = None
    ship_type: int | None = None
    cargo_type: str | None = None
    draft_dm: float | None = None
    ship_length_m: float | None = None
    ship_breadth_m: float | None = None


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
    # Static voyage data (updated as new Msg 5/24 arrive)
    destination: str | None = None
    eta: datetime | None = None
    cargo_type: str | None = None
    draft_dm: float | None = None
    ship_length_m: float | None = None
    ship_breadth_m: float | None = None
    last_static_update: datetime | None = None


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
