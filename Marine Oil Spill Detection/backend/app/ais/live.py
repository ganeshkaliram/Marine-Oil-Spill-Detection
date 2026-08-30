"""Realistic live vessel position simulation.

Generates a fleet of oil/chemical/cargo carriers moving along realistic routes
with:
- Named waypoints (ports, waypoints along shipping lanes)
- Speed variations (acceleration, deceleration, port approach)
- Random AIS-grade position noise (~50m standard deviation)
- Course variations from wind/current drift
- Vessels that pause at waypoints (port calls, anchorage)

To use real AIS, replace :func:`live_vessel_positions` internals with a query to
your AIS feed/DB returning the same schema (API contract is stable).
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field

# Monitoring box (~Gulf of Aden / Bab el-Mandeb region)
_LAT_MIN, _LAT_MAX = 8.0, 13.0
_LON_MIN, _LON_MAX = 8.0, 13.0

_lock = threading.Lock()
_sim_seconds = 0.0
_last_call = time.time()


@dataclass
class Waypoint:
    """A point along a vessel's route."""
    lat: float
    lon: float
    speed_knots: float       # target speed at this waypoint
    dwell_seconds: float = 0.0  # how long to pause here (port call / anchorage)
    name: str = ""


@dataclass
class VesselRoute:
    """A vessel with a multi-waypoint route."""
    mmsi: int
    name: str
    vessel_type: str         # tanker | cargo | chemical
    waypoints: list[Waypoint]
    base_speed: float        # cruise speed in knots
    length_m: float = 200.0  # for AIS static data
    breadth_m: float = 32.0
    cargo_type: str | None = None
    destination: str = ""    # UN/LOCODE

    # Runtime state (tracked externally)
    _current_idx: int = field(default=0, repr=False)
    _segment_progress: float = field(default=0.0, repr=False)
    _dwell_remaining: float = field(default=0.0, repr=False)
    _current_speed: float = field(default=0.0, repr=False)
    _current_cog: float = field(default=0.0, repr=False)


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2 in degrees (0-360)."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# --- Realistic fleet with named waypoints along Gulf of Aden / Red Sea --- #

ROUTES = [
    VesselRoute(
        mmsi=413000111, name="MT SUSPECT-ONE", vessel_type="tanker",
        waypoints=[
            Waypoint(12.80, 43.20, 12.0, name="Mukalla approach"),
            Waypoint(12.50, 43.50, 8.0, name="Offshore anchor"),
            Waypoint(12.00, 44.00, 3.0, 7200, name="Anchorage (discharge)"),
            Waypoint(11.50, 43.80, 10.0, name="Departure"),
            Waypoint(10.50, 43.00, 14.0, name="Bab el-Mandeb"),
        ],
        base_speed=12.0, length_m=183, breadth_m=32, cargo_type="crude-oil",
        destination="SGSIN",
    ),
    VesselRoute(
        mmsi=636000222, name="MV INNOCENT", vessel_type="cargo",
        waypoints=[
            Waypoint(9.50, 10.80, 14.0, name="Port approach"),
            Waypoint(10.00, 10.50, 16.0, 3600, name="Loading berth"),
            Waypoint(10.50, 11.00, 15.0, name="Departure"),
            Waypoint(11.50, 12.00, 16.0, name="Open sea"),
        ],
        base_speed=15.0, length_m=225, breadth_m=32, cargo_type="general-cargo",
        destination="AEJEA",
    ),
    VesselRoute(
        mmsi=538009330, name="MT ALPHA CRUDE", vessel_type="tanker",
        waypoints=[
            Waypoint(11.00, 12.50, 13.0, name="Red Sea approach"),
            Waypoint(10.50, 11.80, 12.0, name="Transit"),
            Waypoint(9.80, 11.00, 11.0, 5400, name="Sheltered anchorage"),
            Waypoint(9.20, 10.50, 13.0, name="Gulf of Aden"),
        ],
        base_speed=12.0, length_m=274, breadth_m=45, cargo_type="lng",
        destination="CNQGD",
    ),
    VesselRoute(
        mmsi=477003410, name="MT BETA CHEM", vessel_type="chemical",
        waypoints=[
            Waypoint(10.20, 9.50, 14.0, name="Coastal transit"),
            Waypoint(10.80, 10.00, 14.0, name="Shipping lane"),
            Waypoint(11.50, 10.80, 14.0, 1800, name="Brief stop"),
            Waypoint(12.00, 11.50, 14.0, name="Red Sea"),
        ],
        base_speed=13.5, length_m=180, breadth_m=28, cargo_type="chemical",
        destination="JEDDAH",
    ),
    VesselRoute(
        mmsi=241002200, name="MT GAMMA FUEL", vessel_type="tanker",
        waypoints=[
            Waypoint(9.50, 11.50, 11.0, name="Fuel terminal approach"),
            Waypoint(10.00, 11.00, 10.5, 10800, name="Bunkering ops"),
            Waypoint(10.50, 10.50, 12.0, name="Departure"),
            Waypoint(11.00, 9.50, 11.0, name="Coastal route"),
        ],
        base_speed=10.5, length_m=140, breadth_m=22, cargo_type="fuel-oil",
        destination="DJJIB",
    ),
    VesselRoute(
        mmsi=255803550, name="MT DELTA LNG", vessel_type="tanker",
        waypoints=[
            Waypoint(12.00, 10.00, 15.0, name="LNG terminal exit"),
            Waypoint(11.50, 10.50, 14.0, name="Transit"),
            Waypoint(10.80, 11.00, 13.0, 2400, name="Anchorage hold"),
            Waypoint(10.00, 11.50, 15.0, name="Southbound"),
        ],
        base_speed=14.0, length_m=300, breadth_m=48, cargo_type="lng",
        destination="SAJED",
    ),
    VesselRoute(
        mmsi=219004414, name="MV EPSILON C", vessel_type="cargo",
        waypoints=[
            Waypoint(10.50, 9.00, 13.0, name="Inbound approach"),
            Waypoint(10.80, 9.80, 13.0, name="Shipping lane"),
            Waypoint(11.20, 10.50, 13.0, 4500, name="Cargo ops"),
            Waypoint(11.00, 11.20, 13.0, name="Departure"),
        ],
        base_speed=13.0, length_m=190, breadth_m=30, cargo_type="containers",
        destination="OMSLL",
    ),
    VesselRoute(
        mmsi=352003720, name="MT ZETA PETRO", vessel_type="chemical",
        waypoints=[
            Waypoint(11.50, 12.00, 10.0, name="Chemical terminal"),
            Waypoint(11.00, 11.50, 9.0, 3600, name="Loading"),
            Waypoint(10.50, 11.00, 10.0, name="Departure"),
            Waypoint(9.80, 10.20, 10.0, name="Gulf transit"),
        ],
        base_speed=9.0, length_m=160, breadth_m=25, cargo_type="chemical",
        destination="EGPSD",
    ),
]


def _update_vessel(v: VesselRoute, dt: float) -> dict:
    """Advance a vessel by `dt` seconds along its route. Returns position dict."""
    wps = v.waypoints
    if not wps:
        return {}

    idx = v._current_idx % len(wps)
    nxt = (v._current_idx + 1) % len(wps)
    wp_from = wps[idx]
    wp_to = wps[nxt]

    # Handle dwell (port call / anchorage)
    if v._dwell_remaining > 0:
        v._dwell_remaining = max(0.0, v._dwell_remaining - dt)
        # Stay at waypoint, speed drops to 0
        v._current_speed = 0.0
        lat, lon = wp_from.lat, wp_from.lon
        return _build_position(v, lat, lon)

    # Calculate segment distance
    dist_km = _haversine_km(wp_from.lat, wp_from.lon, wp_to.lat, wp_to.lon)
    bearing = _bearing_deg(wp_from.lat, wp_from.lon, wp_to.lat, wp_to.lon)

    # Smooth speed transitions (ramp up/down near waypoints)
    if v._segment_progress < 0.15:
        # Accelerating from last waypoint
        speed_factor = v._segment_progress / 0.15
        current_speed = v.base_speed * (0.5 + 0.5 * speed_factor)
    elif v._segment_progress > 0.85:
        # Decelerating toward next waypoint
        speed_factor = (1.0 - v._segment_progress) / 0.15
        current_speed = v.base_speed * (0.5 + 0.5 * speed_factor)
    else:
        current_speed = v.base_speed

    # Apply AIS-grade noise to speed (±10%)
    current_speed *= random.uniform(0.92, 1.08)

    # Convert speed (knots) to distance per second (km)
    km_per_sec = current_speed * 0.000514444
    dist_traveled = km_per_sec * dt

    # Update progress along segment
    v._segment_progress += dist_traveled / max(dist_km, 0.1)

    # Apply drift to bearing (wind/current effect, ±3 degrees)
    drift = random.gauss(0, 1.5)  # Gaussian, ~1.5 degree std dev
    bearing = (bearing + drift) % 360.0

    # Move along great circle
    km_moved = min(dist_traveled, dist_km * (1.0 - v._segment_progress))
    km_moved = max(km_moved, 0.0)

    # Approximate position change (small distance)
    dlat = km_moved * math.cos(math.radians(bearing)) / 111.0
    dlon = km_moved * math.sin(math.radians(bearing)) / (111.0 * math.cos(math.radians(wp_from.lat)))

    lat = wp_from.lat + dlat * v._segment_progress
    lon = wp_from.lon + dlon * v._segment_progress

    v._current_speed = current_speed
    v._current_cog = bearing

    # Check if we've reached the next waypoint
    if v._segment_progress >= 1.0:
        v._current_idx = nxt
        v._segment_progress = 0.0
        v._dwell_remaining = wp_to.dwell_seconds
        lat, lon = wp_to.lat, wp_to.lon

    return _build_position(v, lat, lon)


def _build_position(v: VesselRoute, lat: float, lon: float) -> dict:
    """Build a position dict with AIS-grade noise."""
    # Add position noise (~50m standard deviation, typical for Class A AIS)
    lat += random.gauss(0, 0.00045)  # ~50m at equator
    lon += random.gauss(0, 0.00045)

    # Clamp to monitoring box
    lat = max(_LAT_MIN, min(_LAT_MAX, lat))
    lon = max(_LON_MIN, min(_LON_MAX, lon))

    return {
        "mmsi": v.mmsi,
        "name": v.name,
        "vessel_type": v.vessel_type,
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "sog_knots": round(max(0.0, v._current_speed), 1),
        "cog_deg": round(v._current_cog, 0),
        "destination": v.destination,
        "cargo_type": v.cargo_type,
        "ship_length_m": v.length_m,
        "ship_breadth_m": v.breadth_m,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def live_vessel_positions() -> list[dict]:
    """Return current live vessel positions; advance by real elapsed time.

    This is the primary API consumed by the dashboard. When real AIS data
    is available, this function is replaced by the feed client.
    """
    global _sim_seconds, _last_call
    with _lock:
        now = time.time()
        dt = (now - _last_call)
        if dt < 0 or dt > 300:  # cap at 5 min (laptop sleep)
            dt = 0.0
        _last_call = now
        _sim_seconds += dt

        # Advance all vessels
        out = []
        for v in ROUTES:
            pos = _update_vessel(v, dt)
            if pos:
                out.append(pos)
        return out


def get_vessel_static_data() -> list[dict]:
    """Return static data for all simulated vessels (for AIS Msg 5/24 simulation)."""
    return [
        {
            "mmsi": v.mmsi,
            "vessel_name": v.name,
            "ship_type": {"tanker": 83, "cargo": 31, "chemical": 51}.get(v.vessel_type, 0),
            "vessel_class": v.vessel_type,
            "cargo_type": v.cargo_type,
            "destination": v.destination,
            "ship_length_m": v.length_m,
            "ship_breadth_m": v.breadth_m,
        }
        for v in ROUTES
    ]
