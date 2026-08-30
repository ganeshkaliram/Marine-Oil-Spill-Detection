"""Live vessel position simulation.

Generates a fleet of moving oil / chemical carriers around the monitoring area
so the dashboard renders a MarineTraffic-style live map. Positions advance by the
*real elapsed time between polls*, so the map shows vessels physically moving
(their course/speed respected).

To use real AIS, replace :func:`live_vessel_positions` internals with a query to
your AIS feed/DB returning the same schema (API contract is stable).
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

# Monitoring box (lat/lon) around the demo spill area (~Gulf of Aden region).
_LAT_MIN, _LAT_MAX = 8.0, 13.0
_LON_MIN, _LON_MAX = 8.0, 13.0

_lock = threading.Lock()
_sim_seconds = 0.0    # accumulated simulated travel time
_last_call = time.time()


@dataclass
class Vessel:
    mmsi: int
    name: str
    vessel_type: str        # tanker | cargo | chemical
    start_lat: float
    start_lon: float
    sog_knots: float
    cog_deg: float

    def position_at(self, t: float):
        km = self.sog_knots * t * 0.000514444  # kn * s -> km
        dlat = km * math.cos(math.radians(self.cog_deg)) / 111.0
        dlon = km * math.sin(math.radians(self.cog_deg)) / (111.0 * math.cos(
            math.radians(self.start_lat)))
        return self.start_lat + dlat, self.start_lon + dlon


def _wrap(lat: float, lon: float) -> tuple[float, float]:
    """Wrap a coordinate into the monitoring box (vessels re-enter the area)."""
    span_lat = _LAT_MAX - _LAT_MIN
    span_lon = _LON_MAX - _LON_MIN
    lat = _LAT_MIN + ((lat - _LAT_MIN) % span_lat)
    lon = _LON_MIN + ((lon - _LON_MIN) % span_lon)
    return round(lat, 5), round(lon, 5)


_FLEET = [
    Vessel(413000111, "MT SUSPECT-ONE", "tanker", 10.48, 10.46, 1.2, 165),
    Vessel(636000222, "MV INNOCENT", "cargo", 11.0, 10.2, 16.0, 90),
    Vessel(538009330, "MT ALPHA CRUDE", "tanker", 9.9, 10.8, 12.0, 220),
    Vessel(477003410, "MT BETA CHEM", "chemical", 10.7, 10.1, 14.0, 45),
    Vessel(241002200, "MT GAMMA FUEL", "tanker", 10.3, 11.0, 10.5, 300),
    Vessel(255803550, "MT DELTA LNG", "tanker", 11.2, 10.9, 11.0, 180),
    Vessel(219004414, "MV EPSILON C", "cargo", 9.8, 9.9, 13.5, 75),
    Vessel(352003720, "MT ZETA PETRO", "chemical", 10.6, 10.4, 9.0, 250),
]


def live_vessel_positions() -> list[dict]:
    """Return current live vessel positions; advance by real elapsed time."""
    global _sim_seconds, _last_call
    with _lock:
        now = time.time()
        dt = (now - _last_call) % 60  # cap a jump (e.g. after laptop sleep)
        _last_call = now
        _sim_seconds += dt if dt > 0 else 0.0
        t = _sim_seconds

        out = []
        for v in _FLEET:
            lat, lon = v.position_at(t)
            lat, lon = _wrap(lat, lon)
            out.append({
                "mmsi": v.mmsi,
                "name": v.name,
                "vessel_type": v.vessel_type,
                "lat": lat,
                "lon": lon,
                "sog_knots": round(v.sog_knots, 1),
                "cog_deg": round(v.cog_deg, 0),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            })
        return out
