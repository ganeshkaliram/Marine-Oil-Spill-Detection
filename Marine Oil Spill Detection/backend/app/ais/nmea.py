"""NMEA 0183 sentence parser for AIS data (AIVDM / AIVDO).

Handles:
- Sentence validation (checksum, talker ID)
- Multi-sentence assembly (e.g. Messages 5, 24 span 2 sentences)
- 6-bit ASCII decoding
- Bit-level unpacking for AIS Message Types 1, 2, 3, 4, 5, 18, 19, 24
- Conversion to structured AisMessage / AisStaticData models

AIS data arrives as $AIVDM,... sentences over TCP/UDP (port 4000 typical)
or via HTTP APIs that return raw NMEA lines. This parser converts those
raw bytes into the schema models used by the rest of the pipeline.

Reference: ITU-R M.1371-5 (AIS technical characteristics)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterator

from app.core.schemas import (
    AisMessage,
    AisStaticData,
    AisVesselClass,
    cargo_type_from_codes,
    ship_type_to_class,
)

# NMEA 0183 sentence format:
#   $talkerid,msgtype,...,checksum\r\n
# AIS uses AIVDM (other vessels) and AIVDO (own ship)

_TALKER_IDS = {"AI"}  # AIS transponder
_MAX_SENTENCE_FIELDS = 30
_MIN_PAYLOAD_LEN = 1  # at least 1 character after decoding


def validate_checksum(sentence: str) -> bool:
    """Validate NMEA checksum. The checksum follows '*' and is XOR of all chars between $ and *."""
    if "*" not in sentence:
        return False
    body, cs_hex = sentence.rsplit("*", 1)
    if len(cs_hex) != 2:
        return False
    try:
        expected = int(cs_hex, 16)
    except ValueError:
        return False
    # XOR all characters between $ (or !) and *
    start = 1 if body[0] in ("$", "!") else 0
    computed = 0
    for ch in body[start:]:
        computed ^= ord(ch)
    return computed == expected


def parse_nmea_line(line: str) -> dict | None:
    """Parse a single NMEA sentence and return a dict with its fields.

    Returns None for non-AIS sentences, checksum failures, or malformed input.
    """
    line = line.strip()
    if not line or not line.startswith(("$", "!")):
        return None

    if not validate_checksum(line):
        return None

    body = line.split("*")[0]  # drop checksum
    fields = body.split(",")
    if len(fields) < 2:
        return None

    talker = fields[0][1:]  # strip leading $
    # Standard AIS NMEA uses $AIVDM/$AIVDO. Accept any sentence ending with VDM/VDO.
    sentence_type = talker  # full sentence type e.g. 'AIVDM'
    if sentence_type[-3:] not in ("VDM", "VDO"):
        return None
    msg_type_id = sentence_type  # e.g. 'AIVDM', 'AIVDO'

    # Fields 1-4: fragment count, fragment number, sequential message ID, channel
    try:
        frag_count = int(fields[1]) if fields[1] else 1
        frag_num = int(fields[2]) if fields[2] else 1
    except (ValueError, IndexError):
        return None

    seq_id = fields[3] if len(fields) > 3 else ""
    channel = fields[4] if len(fields) > 4 else ""

    # Field 5: payload (6-bit ASCII encoded)
    payload = fields[5] if len(fields) > 5 else ""
    if not payload:
        return None

    # Field 6: fill bits (0-5)
    try:
        fill_bits = int(fields[6]) if len(fields) > 6 and fields[6] else 0
    except (ValueError, IndexError):
        fill_bits = 0

    return {
        "talker": talker,
        "msg_type": msg_type_id,
        "frag_count": frag_count,
        "frag_num": frag_num,
        "seq_id": seq_id,
        "channel": channel,
        "payload": payload,
        "fill_bits": fill_bits,
        "raw": line,
    }


def decode_6bit_ascii(payload: str) -> bytes:
    """Decode NMEA 6-bit ASCII encoded payload to raw bytes (bit-packed).

    Each character maps to a 6-bit value (0-63). The standard mapping:
    0x30-0x39 -> 0-9   (ASCII '0'-'9')
    0x41-0x5a -> 10-35 (ASCII 'A'-'Z')
    0x60      -> 36    (ASCII '`')
    0x61-0x7a -> 37-61 (ASCII 'a'-'z')
    0x20-0x3f -> 62-63 (space, punctuation)

    Values are packed as a continuous bit stream (MSB first), not as
    individual bytes — matching the AIS specification bit layout.
    """
    result = bytearray()
    bits = 0
    buffer = 0
    for ch in payload:
        c = ord(ch)
        if 0x30 <= c <= 0x39:
            val = c - 0x30
        elif 0x41 <= c <= 0x5a:
            val = c - 0x41 + 10
        elif c == 0x60:
            val = 36
        elif 0x61 <= c <= 0x7a:
            val = c - 0x61 + 37
        elif 0x20 <= c <= 0x3f:
            val = c - 0x20 + 62
        else:
            val = 0
        buffer = (buffer << 6) | val
        bits += 6
        while bits >= 8:
            bits -= 8
            result.append((buffer >> bits) & 0xFF)
    return bytes(result)


def extract_bits(data: bytes, start: int, length: int) -> int:
    """Extract `length` bits from `data` starting at bit position `start`."""
    value = 0
    for i in range(length):
        byte_idx = (start + i) >> 3  # divide by 8
        bit_idx = 7 - ((start + i) & 7)  # bit position within byte (MSB first)
        if byte_idx < len(data):
            value = (value << 1) | ((data[byte_idx] >> bit_idx) & 1)
        else:
            value <<= 1
    return value


def extract_signed_bits(data: bytes, start: int, length: int) -> int:
    """Extract a signed integer from `length` bits (two's complement)."""
    raw = extract_bits(data, start, length)
    # Check sign bit
    if raw >= (1 << (length - 1)):
        raw -= (1 << length)
    return raw


def decode_ascii_field(data: bytes, start: int, length: int) -> str:
    """Decode 6-bit ASCII text from AIS bit data (used in Msg 5, 24)."""
    chars = []
    for i in range(length):
        val = extract_bits(data, start + i * 6, 6)
        if val == 0 or val == 32 or val == 64:
            continue  # skip null/space/@ padding
        if val <= 31:
            # Special characters
            special = {0: " ", 27: "#", 28: "$", 29: "%", 30: "&", 31: "'"}
            chars.append(special.get(val, "?"))
        elif 32 <= val <= 63:
            chars.append(chr(val + 32))
        elif 64 <= val <= 95:
            chars.append(chr(val + 32))
        else:
            chars.append("?")
    return "".join(chars).strip()


def decode_eta(year: int, month: int, day: int, hour: int, minute: int) -> datetime | None:
    """Decode ETA fields from AIS Message 5/24 into a datetime."""
    if year == 0 or month == 0 or day == 0:
        return None
    try:
        return datetime(2000 + year, month, day, hour, minute, tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return None


def _decode_position_type123(data: bytes) -> dict:
    """Decode AIS Message Types 1, 2, 3 (Class A position report)."""
    mmsi = extract_bits(data, 8, 30)
    status = extract_bits(data, 38, 4)  # navigation status
    turn = extract_signed_bits(data, 42, 8)  # rate of turn (x/4 deg/min)
    sog = extract_bits(data, 50, 10) / 10.0  # speed over ground in knots

    # Position (latitude/longitude in 1/10000 minute)
    lon_raw = extract_signed_bits(data, 61, 28)
    lat_raw = extract_signed_bits(data, 89, 27)
    lon = lon_raw / 600000.0
    lat = lat_raw / 600000.0

    cog = extract_bits(data, 116, 12) / 10.0  # course over ground
    heading = extract_bits(data, 128, 9)  # true heading
    second = extract_bits(data, 137, 6)  # timestamp seconds

    return {
        "mmsi": mmsi,
        "lat": lat,
        "lon": lon,
        "sog_knots": sog,
        "cog_deg": cog,
        "heading": heading,
        "nav_status": status,
        "turn_rate": turn,
        "second": second,
    }


def _decode_position_type18(data: bytes) -> dict:
    """Decode AIS Message Type 18 (Class B position report)."""
    mmsi = extract_bits(data, 8, 30)
    reserved = extract_bits(data, 38, 8)
    sog = extract_bits(data, 46, 10) / 10.0

    lon_raw = extract_signed_bits(data, 57, 28)
    lat_raw = extract_signed_bits(data, 85, 27)
    lon = lon_raw / 600000.0
    lat = lat_raw / 600000.0

    cog = extract_bits(data, 112, 12) / 10.0
    heading = extract_bits(data, 124, 9)
    second = extract_bits(data, 133, 6)
    regional = extract_bits(data, 139, 2)

    return {
        "mmsi": mmsi,
        "lat": lat,
        "lon": lon,
        "sog_knots": sog,
        "cog_deg": cog,
        "heading": heading,
        "nav_status": 0,
        "turn_rate": 0,
        "second": second,
    }


def _decode_position_type19(data: bytes) -> dict:
    """Decode AIS Message Type 19 (Class B extended position report)."""
    mmsi = extract_bits(data, 8, 30)
    reserved = extract_bits(data, 38, 8)
    sog = extract_bits(data, 46, 10) / 10.0

    lon_raw = extract_signed_bits(data, 57, 28)
    lat_raw = extract_signed_bits(data, 85, 27)
    lon = lon_raw / 600000.0
    lat = lat_raw / 600000.0

    cog = extract_bits(data, 112, 12) / 10.0
    heading = extract_bits(data, 124, 9)
    second = extract_bits(data, 133, 6)

    # Type 19 includes ship name
    ship_name = decode_ascii_field(data, 143, 120)  # 20 chars x 6 bits

    ship_type = extract_bits(data, 263, 8)
    to_bow = extract_bits(data, 271, 9)
    to_stern = extract_bits(data, 280, 9)
    to_port = extract_bits(data, 289, 5)
    to_starboard = extract_bits(data, 294, 5)
    length = to_bow + to_stern
    breadth = to_port + to_starboard

    return {
        "mmsi": mmsi,
        "lat": lat,
        "lon": lon,
        "sog_knots": sog,
        "cog_deg": cog,
        "heading": heading,
        "nav_status": 0,
        "turn_rate": 0,
        "second": second,
        "ship_name": ship_name,
        "ship_type": ship_type,
        "ship_length_m": float(length) if length else None,
        "ship_breadth_m": float(breadth) if breadth else None,
    }


def _decode_static_type5(data: bytes) -> dict:
    """Decode AIS Message Type 5 (Class A static & voyage data).

    This is the key message for commodity traders — contains:
    - Vessel name, callsign, IMO
    - Ship type (tanker, cargo, chemical, etc.)
    - Destination, ETA
    - Draft (cargo depth)
    """
    mmsi = extract_bits(data, 8, 30)
    ais_version = extract_bits(data, 38, 2)
    imo = extract_bits(data, 40, 30)

    callsign = decode_ascii_field(data, 70, 42)  # 7 chars x 6 bits
    ship_name = decode_ascii_field(data, 112, 120)  # 20 chars x 6 bits

    ship_type = extract_bits(data, 232, 8)

    # Dimensions (to bow, to stern, to port, to starboard)
    to_bow = extract_bits(data, 240, 9)
    to_stern = extract_bits(data, 249, 9)
    to_port = extract_bits(data, 258, 5)
    to_starboard = extract_bits(data, 263, 5)
    length = to_bow + to_stern
    breadth = to_port + to_starboard

    # Position type (1=GPS, 2=GLONASS, etc.)
    pos_type = extract_bits(data, 268, 4)

    # ETA
    eta_month = extract_bits(data, 274, 4)
    eta_day = extract_bits(data, 278, 5)
    eta_hour = extract_bits(data, 283, 5)
    eta_minute = extract_bits(data, 288, 6)
    eta = decode_eta(0, eta_month, eta_day, eta_hour, eta_minute)

    # Present draft in decimetres
    draft = extract_bits(data, 294, 8) / 10.0  # store as metres

    destination = decode_ascii_field(data, 302, 120)  # 20 chars x 6 bits

    dte = bool(extract_bits(data, 422, 1))
    data_terminal = extract_bits(data, 423, 2)

    # cargo_type from ship_type code ranges
    cargo_code = extract_bits(data, 402, 8)  # ship type cargo details (in type 5, bits 402-408 are Spare)
    # Actually the cargo type is embedded in the ship_type field itself for tankers/chemicals

    return {
        "mmsi": mmsi,
        "imo": imo,
        "callsign": callsign,
        "vessel_name": ship_name,
        "ship_type": ship_type,
        "vessel_class": ship_type_to_class(ship_type),
        "cargo_type": None,  # will be derived below
        "destination": destination,
        "eta": eta,
        "draft_dm": draft * 10.0,  # store in decimetres to match schema
        "ship_length_m": float(length) if length else None,
        "ship_breadth_m": float(breadth) if breadth else None,
        "dte": dte,
    }


def _decode_static_type24a(data: bytes) -> dict:
    """Decode AIS Message Type 24 Part A (class B static data)."""
    mmsi = extract_bits(data, 8, 30)
    part_num = extract_bits(data, 38, 2)  # should be 0 for Part A
    ship_name = decode_ascii_field(data, 40, 120)  # 20 chars x 6 bits

    return {
        "mmsi": mmsi,
        "vessel_name": ship_name,
    }


def _decode_static_type24b(data: bytes) -> dict:
    """Decode AIS Message Type 24 Part B (class B static data + ship type)."""
    mmsi = extract_bits(data, 8, 30)
    part_num = extract_bits(data, 38, 2)  # should be 1 for Part B

    ship_type = extract_bits(data, 40, 8)
    vendor_id = decode_ascii_field(data, 48, 42)  # 7 chars x 6 bits
    callsign = decode_ascii_field(data, 90, 42)  # 7 chars x 6 bits

    to_bow = extract_bits(data, 132, 9)
    to_stern = extract_bits(data, 141, 9)
    to_port = extract_bits(data, 150, 5)
    to_starboard = extract_bits(data, 155, 5)
    length = to_bow + to_stern
    breadth = to_port + to_starboard

    return {
        "mmsi": mmsi,
        "ship_type": ship_type,
        "callsign": callsign,
        "vessel_class": ship_type_to_class(ship_type),
        "ship_length_m": float(length) if length else None,
        "ship_breadth_m": float(breadth) if breadth else None,
    }


def _decode_type8(data: bytes) -> dict:
    """Decode AIS Message Type 8 (Binary Broadcast - may carry cargo details)."""
    mmsi = extract_bits(data, 8, 30)
    # DAC 200 = inland waterways; DAC 1 = international (IMO)
    dac = extract_bits(data, 40, 10)
    fi = extract_bits(data, 50, 6)

    result = {"mmsi": mmsi}

    if dac == 1:
        # IMO message types
        if fi == 12:
            # Navigation危险 cargo
            cargo_code = extract_bits(data, 56, 3)
            result["cargo_type_code"] = cargo_code

    return result


class NmeaAisParser:
    """Stateful parser that assembles multi-sentence AIS messages and decodes them.

    Usage:
        parser = NmeaAisParser()
        for line in nmea_source:
            result = parser.process_line(line)
            if result is not None:
                # result is an AisMessage or AisStaticData
                ...
    """

    def __init__(self):
        self._buffer: dict[tuple[str, int], list[dict]] = {}  # (seq_id, frag_count) -> fragments
        self._static_cache: dict[int, dict] = {}  # mmsi -> last static data
        self._seen_names: dict[int, str] = {}  # mmsi -> name (persists)

    def process_line(self, line: str) -> AisMessage | AisStaticData | None:
        """Process a raw NMEA line and return a decoded AIS message, or None."""
        parsed = parse_nmea_line(line)
        if parsed is None:
            return None

        key = (parsed["seq_id"], parsed["frag_count"])

        # Assemble multi-sentence fragments
        if parsed["frag_count"] > 1:
            if key not in self._buffer:
                self._buffer[key] = [None] * parsed["frag_count"]
            idx = parsed["frag_num"] - 1
            if 0 <= idx < len(self._buffer[key]):
                self._buffer[key][idx] = parsed

            # Check if all fragments received
            if all(f is not None for f in self._buffer[key]):
                full_payload = "".join(f["payload"] for f in self._buffer[key])
                fill_bits = self._buffer[key][-1]["fill_bits"]
                del self._buffer[key]
                return self._decode_payload(full_payload, fill_bits)
            return None

        return self._decode_payload(parsed["payload"], parsed["fill_bits"])

    def _decode_payload(self, payload: str, fill_bits: int) -> AisMessage | AisStaticData | None:
        """Decode a complete (possibly assembled) AIS payload."""
        data = decode_6bit_ascii(payload)
        if len(data) < 2:
            return None

        # Remove fill bits from last byte
        if fill_bits > 0 and len(data) > 0:
            mask = 0xFF << fill_bits & 0xFF
            data = bytearray(data)
            data[-1] &= mask if mask else 0
            data = bytes(data)

        msg_type = extract_bits(data, 0, 6)

        try:
            if msg_type in (1, 2, 3):
                decoded = _decode_position_type123(data)
                return self._build_position_message(decoded)
            elif msg_type == 18:
                decoded = _decode_position_type18(data)
                return self._build_position_message(decoded)
            elif msg_type == 19:
                decoded = _decode_position_type19(data)
                mmsi = decoded["mmsi"]
                if decoded.get("ship_name"):
                    self._seen_names[mmsi] = decoded["ship_name"]
                return self._build_position_message(decoded)
            elif msg_type == 5:
                decoded = _decode_static_type5(data)
                return self._build_static_data(decoded)
            elif msg_type == 24:
                part_num = extract_bits(data, 38, 2)
                if part_num == 0:
                    decoded = _decode_static_type24a(data)
                    self._static_cache.setdefault(decoded["mmsi"], {}).update(decoded)
                else:
                    decoded = _decode_static_type24b(data)
                    self._static_cache.setdefault(decoded["mmsi"], {}).update(decoded)
                    if decoded["mmsi"] in self._static_cache:
                        return self._build_static_data(self._static_cache[decoded["mmsi"]])
                return None
            else:
                return None
        except (IndexError, ValueError, OverflowError):
            return None

    def _build_position_message(self, decoded: dict) -> AisMessage:
        """Build an AisMessage from a decoded position report, merging static data if available."""
        mmsi = decoded["mmsi"]
        static = self._static_cache.get(mmsi, {})

        # Use seen name from Type 19 if available
        vessel_name = decoded.get("ship_name") or static.get("vessel_name") or self._seen_names.get(mmsi)

        # Determine vessel class from ship_type if available
        ship_type = decoded.get("ship_type") or static.get("ship_type")
        vessel_class = ship_type_to_class(ship_type)

        # Get static fields
        destination = static.get("destination")
        eta = static.get("eta")
        cargo_type = None
        if ship_type and static.get("ship_type"):
            # Derive cargo type from ship_type (the ship_type itself encodes cargo category)
            cargo_type_map = {
                80: "oil", 81: "lng", 82: "lpg", 83: "chemical",
                84: "oil-imo-ii", 85: "oil-imo-iii", 86: "chemical-imo-ii",
                87: "chemical-imo-iii", 88: "liquid-other",
            }
            cargo_type = cargo_type_map.get(static.get("ship_type"))

        return AisMessage(
            mmsi=mmsi,
            timestamp=datetime.now(timezone.utc),
            lat=decoded["lat"],
            lon=decoded["lon"],
            sog_knots=decoded["sog_knots"],
            cog_deg=decoded["cog_deg"],
            vessel_class=vessel_class,
            vessel_name=vessel_name,
            destination=destination,
            eta=eta,
            ship_type=ship_type,
            cargo_type=cargo_type,
            draft_dm=static.get("draft_dm"),
            ship_length_m=decoded.get("ship_length_m") or static.get("ship_length_m"),
            ship_breadth_m=decoded.get("ship_breadth_m") or static.get("ship_breadth_m"),
        )

    def _build_static_data(self, decoded: dict) -> AisStaticData:
        """Build an AisStaticData from decoded Type 5/24 fields."""
        mmsi = decoded["mmsi"]

        # Update cache
        self._static_cache.setdefault(mmsi, {}).update(decoded)
        if decoded.get("vessel_name"):
            self._seen_names[mmsi] = decoded["vessel_name"]

        ship_type = decoded.get("ship_type")

        # Derive cargo type
        cargo_type = None
        if ship_type is not None:
            cargo_type_map = {
                80: "oil", 81: "lng", 82: "lpg", 83: "chemical",
                84: "oil-imo-ii", 85: "oil-imo-iii", 86: "chemical-imo-ii",
                87: "chemical-imo-iii", 88: "liquid-other",
                50: "chemical-a", 51: "chemical-b", 52: "chemical-c",
            }
            cargo_type = cargo_type_map.get(ship_type)

        return AisStaticData(
            mmsi=mmsi,
            vessel_name=decoded.get("vessel_name"),
            callsign=decoded.get("callsign"),
            imo=decoded.get("imo"),
            ship_type=ship_type,
            vessel_class=ship_type_to_class(ship_type),
            cargo_type=cargo_type,
            destination=decoded.get("destination"),
            eta=decoded.get("eta"),
            draft_dm=decoded.get("draft_dm"),
            ship_length_m=decoded.get("ship_length_m"),
            ship_breadth_m=decoded.get("ship_breadth_m"),
            dte=decoded.get("dte"),
            received_at=datetime.now(timezone.utc),
        )

    def get_static_data(self, mmsi: int) -> dict | None:
        """Get cached static data for a vessel, or None."""
        return self._static_cache.get(mmsi)

    def get_vessel_name(self, mmsi: int) -> str | None:
        """Get the last known vessel name for a given MMSI."""
        return self._seen_names.get(mmsi)


def parse_nmea_stream(lines: Iterator[str]) -> Iterator[AisMessage | AisStaticData]:
    """Convenience: parse a stream of NMEA lines into decoded AIS messages.

    Assembles multi-sentence fragments automatically.
    """
    parser = NmeaAisParser()
    for line in lines:
        result = parser.process_line(line)
        if result is not None:
            yield result
