"""Shared utilities across the pipeline (geo math, logging, ids)."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def gen_id(prefix: str) -> str:
    """Generate a prefixed unique id, e.g. 'slick_1f3a...'."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
