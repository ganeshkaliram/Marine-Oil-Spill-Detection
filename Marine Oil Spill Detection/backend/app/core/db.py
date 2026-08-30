"""SQLite persistence layer for vessel tracks, attribution history, and live state.

Replaces the in-memory store with durable, queryable storage. Designed so
Supabase/Postgres can be swapped in later by changing only this module.

Tables:
    vessels          — latest static data per MMSI
    vessel_positions — time-series of position reports
    vessel_tracks    — aggregated clean tracks with trust scores
    attribution      — attribution reports (correlation cards)
    events           — alert events (spill detections, spoofing flags)
    live_state       — current live state snapshot
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.core.schemas import (
    AisMessage,
    AisStaticData,
    AisVesselClass,
    AttributionReport,
    VesselTrack,
)

logger = logging.getLogger(__name__)

_DB_PATH: Path = settings.DATA_PROCESSED_DIR / "maritime.db"
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-safe SQLite connection."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist (safe to call repeatedly)."""
    conn = _get_conn()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized at %s", _DB_PATH)
    finally:
        conn.close()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vessels (
    mmsi            INTEGER PRIMARY KEY,
    vessel_name     TEXT,
    callsign        TEXT,
    imo             INTEGER,
    ship_type       INTEGER,
    vessel_class    TEXT,
    cargo_type      TEXT,
    destination     TEXT,
    eta             TEXT,
    draft_dm        REAL,
    ship_length_m   REAL,
    ship_breadth_m  REAL,
    last_static_update TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vessel_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mmsi            INTEGER NOT NULL,
    timestamp       TEXT NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    sog_knots       REAL NOT NULL,
    cog_deg         REAL NOT NULL,
    vessel_class    TEXT,
    vessel_name     TEXT,
    destination     TEXT,
    eta             TEXT,
    cargo_type      TEXT,
    draft_dm        REAL,
    ship_length_m   REAL,
    ship_breadth_m  REAL,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_vessel_positions_mmsi ON vessel_positions(mmsi);
CREATE INDEX IF NOT EXISTS idx_vessel_positions_ts ON vessel_positions(timestamp);
CREATE INDEX IF NOT EXISTS idx_vessel_positions_mmsi_ts ON vessel_positions(mmsi, timestamp);

CREATE TABLE IF NOT EXISTS vessel_tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mmsi            INTEGER NOT NULL,
    vessel_name     TEXT,
    vessel_class    TEXT,
    trust_score     REAL NOT NULL,
    point_count     INTEGER NOT NULL,
    anomalies_json  TEXT,
    destination     TEXT,
    eta             TEXT,
    cargo_type      TEXT,
    draft_dm        REAL,
    ship_length_m   REAL,
    ship_breadth_m  REAL,
    start_time      TEXT,
    end_time        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_vessel_tracks_mmsi ON vessel_tracks(mmsi);

CREATE TABLE IF NOT EXISTS attribution (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slick_id        TEXT NOT NULL,
    generated_at    TEXT NOT NULL,
    top_suspect_json TEXT,
    report_json     TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_attribution_slick ON attribution(slick_id);

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    time            TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    slick_id        TEXT,
    vessel_mmsi     INTEGER,
    message         TEXT NOT NULL,
    details_json    TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(time);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

CREATE TABLE IF NOT EXISTS live_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    updated_at      TEXT,
    state_json      TEXT NOT NULL
);
"""


class MaritimeDb:
    """Thread-safe interface to the maritime SQLite database."""

    def __init__(self):
        init_db()

    # ---- Vessels (static data) ---- #

    def upsert_vessel(self, static: AisStaticData) -> None:
        """Insert or update static vessel data."""
        with _lock:
            conn = _get_conn()
            try:
                conn.execute(
                    """INSERT INTO vessels (mmsi, vessel_name, callsign, imo, ship_type,
                       vessel_class, cargo_type, destination, eta, draft_dm,
                       ship_length_m, ship_breadth_m, last_static_update, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                       ON CONFLICT(mmsi) DO UPDATE SET
                       vessel_name=COALESCE(excluded.vessel_name, vessels.vessel_name),
                       callsign=COALESCE(excluded.callsign, vessels.callsign),
                       imo=COALESCE(excluded.imo, vessels.imo),
                       ship_type=COALESCE(excluded.ship_type, vessels.ship_type),
                       vessel_class=COALESCE(excluded.vessel_class, vessels.vessel_class),
                       cargo_type=COALESCE(excluded.cargo_type, vessels.cargo_type),
                       destination=COALESCE(excluded.destination, vessels.destination),
                       eta=COALESCE(excluded.eta, vessels.eta),
                       draft_dm=COALESCE(excluded.draft_dm, vessels.draft_dm),
                       ship_length_m=COALESCE(excluded.ship_length_m, vessels.ship_length_m),
                       ship_breadth_m=COALESCE(excluded.ship_breadth_m, vessels.ship_breadth_m),
                       last_static_update=excluded.last_static_update,
                       updated_at=datetime('now')""",
                    (
                        static.mmsi, static.vessel_name, static.callsign,
                        static.imo, static.ship_type,
                        static.vessel_class.value if static.vessel_class else None,
                        static.cargo_type, static.destination,
                        static.eta.isoformat() if static.eta else None,
                        static.draft_dm, static.ship_length_m, static.ship_breadth_m,
                        static.received_at.isoformat() if static.received_at else None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_vessel(self, mmsi: int) -> dict | None:
        """Get static data for a vessel."""
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM vessels WHERE mmsi=?", (mmsi,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_vessels(self) -> list[dict]:
        """Get all known vessels."""
        conn = _get_conn()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM vessels ORDER BY vessel_name").fetchall()]
        finally:
            conn.close()

    # ---- Position reports ---- #

    def insert_positions(self, messages: list[AisMessage]) -> int:
        """Bulk insert position reports. Returns count inserted."""
        if not messages:
            return 0
        with _lock:
            conn = _get_conn()
            try:
                rows = [
                    (
                        m.mmsi,
                        m.timestamp.isoformat(),
                        m.lat, m.lon,
                        m.sog_knots, m.cog_deg,
                        m.vessel_class.value if m.vessel_class else None,
                        m.vessel_name, m.destination,
                        m.eta.isoformat() if m.eta else None,
                        m.cargo_type, m.draft_dm,
                        m.ship_length_m, m.ship_breadth_m,
                    )
                    for m in messages
                ]
                conn.executemany(
                    """INSERT INTO vessel_positions
                       (mmsi, timestamp, lat, lon, sog_knots, cog_deg,
                        vessel_class, vessel_name, destination, eta,
                        cargo_type, draft_dm, ship_length_m, ship_breadth_m)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
                conn.commit()
                return len(rows)
            finally:
                conn.close()

    def get_positions(
        self,
        mmsi: int | None = None,
        since: str | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Query position reports with optional filters."""
        conn = _get_conn()
        try:
            query = "SELECT * FROM vessel_positions WHERE 1=1"
            params: list = []
            if mmsi is not None:
                query += " AND mmsi=?"
                params.append(mmsi)
            if since is not None:
                query += " AND timestamp>=?"
                params.append(since)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            return [dict(r) for r in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    # ---- Vessel tracks ---- #

    def insert_track(self, track: VesselTrack) -> int:
        """Insert an aggregated vessel track."""
        with _lock:
            conn = _get_conn()
            try:
                start = min((p.timestamp for p in track.points), default=None)
                end = max((p.timestamp for p in track.points), default=None)
                cur = conn.execute(
                    """INSERT INTO vessel_tracks
                       (mmsi, vessel_name, vessel_class, trust_score, point_count,
                        anomalies_json, destination, eta, cargo_type, draft_dm,
                        ship_length_m, ship_breadth_m, start_time, end_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        track.mmsi, track.vessel_name,
                        track.vessel_class.value if track.vessel_class else None,
                        track.trust_score, len(track.points),
                        json.dumps([a.model_dump(mode="json") for a in track.anomalies]),
                        track.destination,
                        track.eta.isoformat() if track.eta else None,
                        track.cargo_type, track.draft_dm,
                        track.ship_length_m, track.ship_breadth_m,
                        start.isoformat() if start else None,
                        end.isoformat() if end else None,
                    ),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def replace_tracks(self, tracks: list[VesselTrack]) -> int:
        """Replace all tracks with fresh data (used on each poll cycle)."""
        with _lock:
            conn = _get_conn()
            try:
                conn.execute("DELETE FROM vessel_tracks")
                count = 0
                for track in tracks:
                    start = min((p.timestamp for p in track.points), default=None)
                    end = max((p.timestamp for p in track.points), default=None)
                    conn.execute(
                        """INSERT INTO vessel_tracks
                           (mmsi, vessel_name, vessel_class, trust_score, point_count,
                            anomalies_json, destination, eta, cargo_type, draft_dm,
                            ship_length_m, ship_breadth_m, start_time, end_time)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            track.mmsi, track.vessel_name,
                            track.vessel_class.value if track.vessel_class else None,
                            track.trust_score, len(track.points),
                            json.dumps([a.model_dump(mode="json") for a in track.anomalies]),
                            track.destination,
                            track.eta.isoformat() if track.eta else None,
                            track.cargo_type, track.draft_dm,
                            track.ship_length_m, track.ship_breadth_m,
                            start.isoformat() if start else None,
                            end.isoformat() if end else None,
                        ),
                    )
                    count += 1
                conn.commit()
                return count
            finally:
                conn.close()

    def get_tracks(self, mmsi: int | None = None) -> list[dict]:
        """Query vessel tracks."""
        conn = _get_conn()
        try:
            if mmsi is not None:
                rows = conn.execute(
                    "SELECT * FROM vessel_tracks WHERE mmsi=? ORDER BY created_at DESC",
                    (mmsi,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM vessel_tracks ORDER BY trust_score DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- Attribution reports ---- #

    def insert_attribution(self, report: AttributionReport) -> int:
        """Store an attribution report."""
        with _lock:
            conn = _get_conn()
            try:
                cur = conn.execute(
                    """INSERT INTO attribution (slick_id, generated_at, top_suspect_json, report_json)
                       VALUES (?, ?, ?, ?)""",
                    (
                        report.slick_id,
                        report.generated_at.isoformat(),
                        json.dumps(report.top_suspect.model_dump(mode="json")) if report.top_suspect else None,
                        json.dumps(report.model_dump(mode="json")),
                    ),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def get_attribution(self, slick_id: str | None = None, limit: int = 50) -> list[dict]:
        """Query attribution reports."""
        conn = _get_conn()
        try:
            if slick_id is not None:
                rows = conn.execute(
                    "SELECT * FROM attribution WHERE slick_id=? ORDER BY created_at DESC LIMIT ?",
                    (slick_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM attribution ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- Events ---- #

    def insert_event(self, event: dict) -> None:
        """Store an alert event."""
        with _lock:
            conn = _get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO events (id, time, event_type, slick_id, vessel_mmsi, message, details_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event["id"],
                        event["time"],
                        event.get("event_type", "alert"),
                        event.get("slick_id"),
                        event.get("vessel_mmsi"),
                        event["message"],
                        json.dumps(event.get("details")) if event.get("details") else None,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_events(self, event_type: str | None = None, limit: int = 50) -> list[dict]:
        """Query events."""
        conn = _get_conn()
        try:
            if event_type is not None:
                rows = conn.execute(
                    "SELECT * FROM events WHERE event_type=? ORDER BY time DESC LIMIT ?",
                    (event_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY time DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ---- Live state snapshot ---- #

    def save_live_state(self, state: dict) -> None:
        """Save the current live state snapshot."""
        with _lock:
            conn = _get_conn()
            try:
                conn.execute(
                    """INSERT INTO live_state (id, updated_at, state_json)
                       VALUES (1, datetime('now'), ?)
                       ON CONFLICT(id) DO UPDATE SET
                       updated_at=datetime('now'), state_json=excluded.state_json""",
                    (json.dumps(state),),
                )
                conn.commit()
            finally:
                conn.close()

    def get_live_state(self) -> dict | None:
        """Get the current live state snapshot."""
        conn = _get_conn()
        try:
            row = conn.execute("SELECT state_json FROM live_state WHERE id=1").fetchone()
            if row:
                return json.loads(row["state_json"])
            return None
        finally:
            conn.close()

    # ---- Stats ---- #

    def get_stats(self) -> dict:
        """Get database statistics."""
        conn = _get_conn()
        try:
            stats = {}
            for table in ("vessels", "vessel_positions", "vessel_tracks", "attribution", "events"):
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                stats[table] = row["cnt"]
            return stats
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_db: MaritimeDb | None = None


def get_db() -> MaritimeDb:
    """Get or create the global database singleton."""
    global _db
    if _db is None:
        _db = MaritimeDb()
    return _db
