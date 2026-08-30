from __future__ import annotations

from app.core.drift import backtrack_particles
from app.core.schemas import SlickGeometry


def test_backtrack_basic():
    geom = SlickGeometry(centroid_lat=10.5, centroid_lon=10.5, area_m2=1e6, perimeter_m=1000, bbox_px=(0,0,10,10), pixel_coords=[])
    particles = backtrack_particles(geom, hours=6.0, n_particles=100, dt_hours=1.0)
    assert isinstance(particles, list)
    assert len(particles) == 100
    lat0, lon0 = particles[0]
    assert isinstance(lat0, float) and isinstance(lon0, float)
