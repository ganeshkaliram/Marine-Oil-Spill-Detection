"""In-memory AIS track store (replaced by a DB-backed store later).

For the scaffold this holds cleaned VesselTracks so the attribution endpoint has
something to query without requiring Kafka/PostGIS setup. The module is import
guarded in the API so its absence does not crash the app.
"""

from __future__ import annotations

from app.core.schemas import VesselTrack

# Populated by scripts/ingest_ais.py during development.
in_memory_tracks: list[VesselTrack] = []
