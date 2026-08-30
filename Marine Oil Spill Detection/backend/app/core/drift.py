from __future__ import annotations

import math
from typing import Callable, Iterable

import numpy as np

from app.core.schemas import SlickGeometry


def _deg_per_km(lat: float) -> float:
    """Approximate conversion: degrees latitude per km (constant) and degrees
    longitude per km depend on latitude."""
    return 1.0 / 111.0


def _deg_lon_per_km(lat: float) -> float:
    # avoid division by zero at poles
    return 1.0 / (111.0 * max(0.0001, math.cos(math.radians(lat))))


def synthetic_current(lat: np.ndarray | float, lon: np.ndarray | float, t_hours: float) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic, time-varying current field (km/h).

    This lightweight analytic field is intentionally simple and deterministic for
    demo/harness use. It returns (u_east_km_h, v_north_km_h). Inputs may be
    scalars or numpy arrays (vectorised).
    """
    lat_a = np.array(lat, copy=False)
    lon_a = np.array(lon, copy=False)
    phase = 2.0 * math.pi * (t_hours % 24.0) / 24.0

    # Base eastward drift + weak latitudinal modulation
    u = 0.5 + 0.2 * np.sin(np.radians(lat_a)) * np.cos(phase)
    # Base northward drift + longitudinal modulation
    v = 0.2 + 0.15 * np.cos(np.radians(lon_a)) * np.sin(phase)

    return u, v


def backtrack_particles(
    geom: SlickGeometry,
    hours: float = 24.0,
    n_particles: int = 500,
    dt_hours: float = 1.0,
    current_fn: Callable[[np.ndarray, np.ndarray, float], tuple[np.ndarray, np.ndarray]] = synthetic_current,
) -> list[tuple[float, float]]:
    """Backtrack an ensemble of particles from a detected slick centroid.

    Simplified particle advection (Euler scheme) using a synthetic current
    field. Returns a list of (lat, lon) coordinates representing probable origin
    cloud after "hours" of backward integration.

    This demo-oriented implementation avoids heavy dependencies and large
    oceanographic data downloads. For production, replace `current_fn` with a
    function that queries gridded ocean current datasets and uses RK4 integration.
    """
    rng = np.random.default_rng(seed=42)

    center_lat = geom.centroid_lat
    center_lon = geom.centroid_lon

    # approximate radial spread from area (m^2) -> radius (deg)
    try:
        radius_m = math.sqrt(geom.area_m2 / math.pi)  # meters
    except Exception:
        radius_m = 2000.0
    radius_km = max(0.5, radius_m / 1000.0)
    sigma_deg = radius_km * _deg_per_km(center_lat) * 0.5

    lats = center_lat + rng.normal(0.0, sigma_deg, size=n_particles)
    lons = center_lon + rng.normal(0.0, sigma_deg, size=n_particles)

    steps = max(1, int(math.ceil(hours / dt_hours)))
    t = 0.0

    for _ in range(steps):
        u_km_h, v_km_h = current_fn(lats, lons, t)
        # backtracking: move particles upstream (subtract displacement)
        dlat = (v_km_h * dt_hours) * _deg_per_km(center_lat)  # deg latitude
        # longitude scaling per-particle
        lon_deg_per_km = 1.0 / (111.0 * np.cos(np.radians(lats)))
        dlon = (u_km_h * dt_hours) * lon_deg_per_km

        lats = lats - dlat
        lons = lons - dlon
        t += dt_hours

    return list(zip(lats.tolist(), lons.tolist()))
