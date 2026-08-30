"""Tests for NMEA 0183 parser, AIS feed client, database, and updated schemas."""

from __future__ import annotations

import json
import math
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.ais.nmea import (
    NmeaAisParser,
    decode_6bit_ascii,
    decode_eta,
    extract_bits,
    extract_signed_bits,
    decode_ascii_field,
    parse_nmea_line,
    parse_nmea_stream,
    validate_checksum,
)
from app.core.schemas import (
    AisMessage,
    AisStaticData,
    AisVesselClass,
    VesselTrack,
    cargo_type_from_codes,
    ship_type_to_class,
)


# ---------------------------------------------------------------------------
# NMEA checksum and parsing
# ---------------------------------------------------------------------------

class TestNmeaChecksum:
    def test_valid_checksum(self):
        # $AIVDM,1,1,,B,15MgKj0P0wJGDrN0EJ9p;4`220RSS,0*6A (example)
        # We'll construct a valid one
        body = "$AIVDM,1,1,,A,15MgKj0P0wJGDrN0EJ9p;4`220RSS,0"
        cs = 0
        for ch in body[1:]:  # skip $
            cs ^= ord(ch)
        sentence = f"{body}*{cs:02X}"
        assert validate_checksum(sentence) is True

    def test_invalid_checksum(self):
        assert validate_checksum("$AIVDM,1,1,,A,test,0*00") is False

    def test_no_checksum(self):
        assert validate_checksum("$AIVDM,1,1,,A,test") is False

    def test_malformed_checksum(self):
        assert validate_checksum("$AIVDM,1,1,,A,test,0*XYZ") is False


class TestNmeaLineParsing:
    def test_non_ais_talker(self):
        assert parse_nmea_line("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A") is None

    def test_empty_line(self):
        assert parse_nmea_line("") is None
        assert parse_nmea_line("   ") is None

    def test_non_nmea(self):
        assert parse_nmea_line("not an NMEA sentence") is None

    def test_ais_sentence_fields(self):
        # Construct a valid AIVDM sentence with a proper Type 18 payload
        # NMEA format: $AIVDM,frag_count,frag_num,seq_id,channel,payload,fill_bits*CS
        # Type 18 = 0b010010 = 18 decimal -> 6-bit char = 'I'
        # Need 20 chars for valid Type 18 (120 bits > 112 needed)
        body = "$AIVDM,1,1,,B,IRRRRRRRRRRRRRRRRRRR,0"
        cs = 0
        for ch in body[1:]:
            cs ^= ord(ch)
        sentence = f"{body}*{cs:02X}"
        result = parse_nmea_line(sentence)
        assert result is not None, f"Failed to parse: {sentence}"
        assert result["talker"] == "AIVDM"
        assert result["msg_type"] == "AIVDM"
        assert result["frag_count"] == 1
        assert result["frag_num"] == 1
        assert result["channel"] == "B"
        assert result["payload"] == "IRRRRRRRRRRRRRRRRRRR"


# ---------------------------------------------------------------------------
# 6-bit ASCII decoding
# ---------------------------------------------------------------------------

class Test6BitAscii:
    def test_decode_known_chars(self):
        # 6-bit values are bit-packed into bytes (MSB first)
        # '1' = value 1 = 000001, '0' = value 0 = 000000
        # '10' -> 000001|000000 = 00000100|0000 = byte 0x04, 4 bits left
        data = decode_6bit_ascii("10")
        assert len(data) == 1
        assert data[0] == 0x04

        # 'AA' -> 001010|001010 = 00101000|1010 = byte 0x28
        assert decode_6bit_ascii("AA")[0] == 0x28

        # '00' -> 000000|000000 = 0x00
        assert decode_6bit_ascii("00")[0] == 0x00

        # Verify bit extraction works on packed result
        assert extract_bits(data, 0, 6) == 1  # first 6-bit value is '1'

    def test_decode_empty(self):
        assert decode_6bit_ascii("") == b""


# ---------------------------------------------------------------------------
# Bit extraction
# ---------------------------------------------------------------------------

class TestBitExtraction:
    def test_extract_bits(self):
        data = bytes([0b10110100, 0b11001010])
        # First 4 bits: 1011 = 11
        assert extract_bits(data, 0, 4) == 0b1011
        # Next 4 bits: 0100 = 4
        assert extract_bits(data, 4, 4) == 0b0100
        # 8 bits starting at bit 4: 01001100 = 76
        assert extract_bits(data, 4, 8) == 0b01001100

    def test_extract_signed_positive(self):
        data = bytes([0b00000101])  # +5
        assert extract_signed_bits(data, 0, 8) == 5

    def test_extract_signed_negative(self):
        data = bytes([0b11111011])  # -5 in 8-bit two's complement
        assert extract_signed_bits(data, 0, 8) == -5


# ---------------------------------------------------------------------------
# ETA decoding
# ---------------------------------------------------------------------------

class TestEtaDecoding:
    def test_valid_eta(self):
        eta = decode_eta(26, 8, 30, 14, 30)
        assert eta is not None
        assert eta.year == 2026
        assert eta.month == 8
        assert eta.day == 30
        assert eta.hour == 14
        assert eta.minute == 30

    def test_zero_eta(self):
        assert decode_eta(0, 0, 0, 0, 0) is None
        assert decode_eta(26, 0, 0, 0, 0) is None

    def test_invalid_eta(self):
        assert decode_eta(26, 13, 32, 25, 61) is None


# ---------------------------------------------------------------------------
# Ship type classification
# ---------------------------------------------------------------------------

class TestShipTypeClassification:
    def test_tanker_codes(self):
        assert ship_type_to_class(80) == AisVesselClass.TANKER
        assert ship_type_to_class(83) == AisVesselClass.TANKER
        assert ship_type_to_class(89) == AisVesselClass.TANKER

    def test_cargo_codes(self):
        assert ship_type_to_class(30) == AisVesselClass.CARGO
        assert ship_type_to_class(31) == AisVesselClass.CARGO
        assert ship_type_to_class(39) == AisVesselClass.CARGO

    def test_chemical_codes(self):
        assert ship_type_to_class(50) == AisVesselClass.OTHER  # hazardous-b

    def test_none_code(self):
        assert ship_type_to_class(None) is None

    def test_cargo_type_tanker(self):
        # Ship type 83 (80-89 range) = tanker category
        # cargo code 1 = oil, 2 = lng, 3 = lpg, 4 = chemical
        assert cargo_type_from_codes(80, 1) == "oil"
        assert cargo_type_from_codes(81, 2) == "lng"
        assert cargo_type_from_codes(82, 3) == "lpg"
        assert cargo_type_from_codes(83, 4) == "chemical"

    def test_cargo_type_none(self):
        assert cargo_type_from_codes(None, 1) is None
        assert cargo_type_from_codes(80, None) is None


# ---------------------------------------------------------------------------
# NMEA Parser (stateful)
# ---------------------------------------------------------------------------

class TestNmeaParser:
    def test_parser_returns_none_for_non_ais(self):
        parser = NmeaAisParser()
        assert parser.process_line("") is None
        assert parser.process_line("not nmea") is None

    def test_single_sentence_assembly(self):
        parser = NmeaAisParser()
        # Single-sentence Type 18 message (all zeros = MMSI 0 at 0,0)
        # We'll construct a minimal payload
        # For now just verify parser doesn't crash on malformed data
        result = parser.process_line("$AIVDM,1,1,,A,0000000000,0*18")
        # May or may not decode, but should not crash
        assert result is None or isinstance(result, (AisMessage, AisStaticData))


# ---------------------------------------------------------------------------
# Updated schema fields
# ---------------------------------------------------------------------------

class TestUpdatedSchemas:
    def test_ais_message_extended_fields(self):
        msg = AisMessage(
            mmsi=413000111,
            timestamp=datetime.now(timezone.utc),
            lat=10.5,
            lon=10.5,
            sog_knots=12.0,
            cog_deg=180.0,
            vessel_class=AisVesselClass.TANKER,
            vessel_name="MT TEST",
            destination="SGSIN",
            eta=datetime(2026, 9, 1, tzinfo=timezone.utc),
            cargo_type="crude-oil",
            draft_dm=12.5,
            ship_length_m=183.0,
            ship_breadth_m=32.0,
        )
        assert msg.vessel_name == "MT TEST"
        assert msg.destination == "SGSIN"
        assert msg.cargo_type == "crude-oil"
        assert msg.draft_dm == 12.5

    def test_ais_static_data(self):
        static = AisStaticData(
            mmsi=413000111,
            vessel_name="MT TEST",
            imo=9876543,
            ship_type=83,
            cargo_type="chemical",
            destination="JEDDAH",
            eta=datetime(2026, 9, 5, 14, 30, tzinfo=timezone.utc),
            draft_dm=15.0,
        )
        assert static.imo == 9876543
        assert static.ship_type == 83
        assert static.cargo_type == "chemical"

    def test_vessel_track_extended_fields(self):
        msg = AisMessage(
            mmsi=1, timestamp=datetime.now(timezone.utc),
            lat=10.0, lon=10.0, sog_knots=10.0, cog_deg=90.0,
        )
        track = VesselTrack(
            mmsi=1, points=[msg], trust_score=1.0,
            destination="SGSIN",
            eta=datetime(2026, 9, 1, tzinfo=timezone.utc),
            cargo_type="crude-oil",
            draft_dm=12.5,
            ship_length_m=183.0,
            ship_breadth_m=32.0,
        )
        assert track.destination == "SGSIN"
        assert track.cargo_type == "crude-oil"
        assert track.draft_dm == 12.5


# ---------------------------------------------------------------------------
# AIS Feed Client (unit tests)
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed(self):
        from app.ais.feed import CircuitBreaker
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        from app.ais.feed import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=1)
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self):
        from app.ais.feed import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_success_resets(self):
        from app.ais.feed import CircuitBreaker
        cb = CircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------

class TestDatabase:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path):
        """Create a fresh temp database for each test."""
        import app.core.db as db_mod
        from app.config import settings
        # Override DB path for testing
        test_db = tmp_path / "test_maritime.db"
        original_path = db_mod._DB_PATH
        db_mod._DB_PATH = test_db
        # Reset singleton
        db_mod._db = None
        yield
        db_mod._DB_PATH = original_path
        db_mod._db = None

    def test_upsert_and_get_vessel(self):
        from app.core.db import get_db
        db = get_db()
        static = AisStaticData(
            mmsi=413000111,
            vessel_name="MT TEST",
            ship_type=83,
            cargo_type="chemical",
            destination="SGSIN",
            eta=datetime(2026, 9, 1, tzinfo=timezone.utc),
            draft_dm=12.5,
        )
        db.upsert_vessel(static)
        vessel = db.get_vessel(413000111)
        assert vessel is not None
        assert vessel["vessel_name"] == "MT TEST"
        assert vessel["cargo_type"] == "chemical"
        assert vessel["destination"] == "SGSIN"

    def test_upsert_updates_existing(self):
        from app.core.db import get_db
        db = get_db()
        static1 = AisStaticData(mmsi=413000111, vessel_name="MT V1")
        db.upsert_vessel(static1)
        static2 = AisStaticData(mmsi=413000111, vessel_name="MT V2", destination="JEDDAH")
        db.upsert_vessel(static2)
        vessel = db.get_vessel(413000111)
        assert vessel["vessel_name"] == "MT V2"
        assert vessel["destination"] == "JEDDAH"

    def test_insert_and_query_positions(self):
        from app.core.db import get_db
        db = get_db()
        now = datetime.now(timezone.utc)
        messages = [
            AisMessage(mmsi=1, timestamp=now, lat=10.0, lon=10.0, sog_knots=10.0, cog_deg=90.0),
            AisMessage(mmsi=1, timestamp=now + timedelta(minutes=1), lat=10.1, lon=10.1, sog_knots=10.0, cog_deg=90.0),
        ]
        count = db.insert_positions(messages)
        assert count == 2
        positions = db.get_positions(mmsi=1)
        assert len(positions) == 2

    def test_replace_tracks(self):
        from app.core.db import get_db
        db = get_db()
        now = datetime.now(timezone.utc)
        msg = AisMessage(mmsi=1, timestamp=now, lat=10.0, lon=10.0, sog_knots=10.0, cog_deg=90.0)
        tracks = [
            VesselTrack(mmsi=1, points=[msg], trust_score=1.0),
            VesselTrack(mmsi=2, points=[msg], trust_score=0.8),
        ]
        db.replace_tracks(tracks)
        result = db.get_tracks()
        assert len(result) == 2

    def test_events(self):
        from app.core.db import get_db
        db = get_db()
        event = {
            "id": "evt_123",
            "time": datetime.now(timezone.utc).isoformat(),
            "event_type": "spill_attribution",
            "message": "ALERT Spill detected",
        }
        db.insert_event(event)
        events = db.get_events()
        assert len(events) == 1
        assert events[0]["id"] == "evt_123"

    def test_live_state(self):
        from app.core.db import get_db
        db = get_db()
        state = {"vessels": 5, "alerts": 2}
        db.save_live_state(state)
        loaded = db.get_live_state()
        assert loaded == state

    def test_stats(self):
        from app.core.db import get_db
        db = get_db()
        stats = db.get_stats()
        assert "vessels" in stats
        assert "vessel_positions" in stats


# ---------------------------------------------------------------------------
# Live vessel simulation
# ---------------------------------------------------------------------------

class TestLiveVessels:
    def test_positions_in_monitoring_box(self):
        from app.ais.live import live_vessel_positions
        pos = live_vessel_positions()
        assert len(pos) > 0
        for v in pos:
            assert 8.0 <= v["lat"] <= 13.0
            assert 8.0 <= v["lon"] <= 13.0
            for key in ("mmsi", "name", "vessel_type", "lat", "lon", "sog_knots", "cog_deg"):
                assert key in v

    def test_trader_fields_present(self):
        from app.ais.live import live_vessel_positions
        pos = live_vessel_positions()
        for v in pos:
            # New trader-critical fields should be present
            assert "destination" in v
            assert "cargo_type" in v

    def test_vessels_move_over_time(self):
        from app.ais.live import live_vessel_positions
        a = {v["mmsi"]: (v["lat"], v["lon"]) for v in live_vessel_positions()}
        time.sleep(1.2)
        b = {v["mmsi"]: (v["lat"], v["lon"]) for v in live_vessel_positions()}
        moved = any(b[m] != a.get(m) for m in a)
        assert moved is True

    def test_static_data_available(self):
        from app.ais.live import get_vessel_static_data
        static = get_vessel_static_data()
        assert len(static) > 0
        for s in static:
            assert "mmsi" in s
            assert "vessel_name" in s
            assert "cargo_type" in s
            assert "destination" in s
