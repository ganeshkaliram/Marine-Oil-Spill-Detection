"""Real-time AIS data feed client with HTTP polling, retry, and circuit breaker.

Supports multiple AIS data providers:
- MarineCadastre (free bulk historical data)
- AISHub (free real-time API with registration)
- OpenSeaMap / custom TCP streams
- Fallback to synthetic simulation

The client polls an HTTP endpoint for NMEA lines, parses them through the
NMEA parser, builds clean vessel tracks via the anomaly detector, and
publishes results to a callback or in-memory store.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Callable

from app.ais.nmea import NmeaAisParser, parse_nmea_line
from app.ais.service import AisAnomalyDetector, AisProcessingService
from app.config import settings
from app.core.schemas import AisMessage, AisStaticData, VesselTrack

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Simple circuit breaker to avoid hammering a failed AIS feed.

    States:
        CLOSED  -> normal operation, requests go through
        OPEN    -> feed is failing, skip requests for `reset_timeout` seconds
        HALF_OPEN -> after timeout, allow one probe request
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = self.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.warning(
                "Circuit breaker OPEN: %d consecutive failures, "
                "will retry in %.0fs",
                self.failure_count, self.reset_timeout,
            )

    def allow_request(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.monotonic() - self.last_failure_time >= self.reset_timeout:
                self.state = self.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow one probe
        return True


class AisFeedClient:
    """Polls an AIS data provider and yields decoded AIS messages.

    Features:
    - Exponential backoff with jitter on transient failures
    - Circuit breaker to stop hammering a dead feed
    - NMEA parsing with multi-sentence assembly
    - Anomaly detection on incoming streams
    - Configurable poll interval
    - Graceful fallback to synthetic data

    Usage:
        client = AisFeedClient()
        client.start()  # runs in background thread
        # ... later ...
        client.stop()
    """

    def __init__(
        self,
        feed_url: str | None = None,
        poll_interval: float | None = None,
        on_messages: Callable[[list[AisMessage]], None] | None = None,
        on_static: Callable[[AisStaticData], None] | None = None,
    ):
        self.feed_url = feed_url or settings.AIS_FEED_URL
        self.poll_interval = poll_interval or settings.AIS_POLL_INTERVAL_SEC
        self.on_messages = on_messages
        self.on_static = on_static

        self._parser = NmeaAisParser()
        self._anomaly_detector = AisAnomalyDetector()
        self._processing = AisProcessingService(self._anomaly_detector)
        self._circuit = CircuitBreaker(
            failure_threshold=settings.AIS_CIRCUIT_BREAKER_THRESHOLD,
            reset_timeout=settings.AIS_CIRCUIT_BREAKER_RESET_SEC,
        )

        self._running = False
        self._thread = None

        # Accumulated state
        self._position_buffer: list[AisMessage] = []
        self._static_data: dict[int, AisStaticData] = {}
        self._tracks: list[VesselTrack] = []
        self._last_poll: datetime | None = None
        self._consecutive_failures = 0
        self._backoff_base = 2.0
        self._backoff_max = 120.0

    def fetch_nmea_lines(self) -> list[str]:
        """Fetch raw NMEA lines from the configured feed URL.

        Returns a list of raw NMEA sentence strings.
        Raises FeedError on non-retryable failures.
        Raises FeedTransientError on retryable failures (timeout, 5xx, etc.).
        """
        if not self.feed_url:
            raise FeedError("No AIS feed URL configured")

        try:
            req = urllib.request.Request(
                self.feed_url,
                headers={
                    "User-Agent": "MarineOilSpillMonitor/1.0",
                    "Accept": "text/plain, application/x-ndjson, application/json",
                },
            )

            # Add API key if configured
            if settings.AIS_API_KEY:
                req.add_header("Authorization", f"Bearer {settings.AIS_API_KEY}")

            with urllib.request.urlopen(req, timeout=settings.AIS_REQUEST_TIMEOUT_SEC) as resp:
                data = resp.read().decode("utf-8", errors="replace")

                # Handle different response formats
                content_type = resp.headers.get("Content-Type", "")

                if "application/json" in content_type or "ndjson" in content_type:
                    # JSON/NDJSON response — each line is a JSON object with nmea field
                    lines = []
                    for line in data.strip().split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if "nmea" in obj:
                                if isinstance(obj["nmea"], list):
                                    lines.extend(obj["nmea"])
                                else:
                                    lines.append(obj["nmea"])
                            elif "sentence" in obj:
                                lines.append(obj["sentence"])
                            elif "raw" in obj:
                                lines.append(obj["raw"])
                        except json.JSONDecodeError:
                            continue
                    return lines
                else:
                    # Plain text NMEA — each line is a sentence
                    return [
                        line.strip()
                        for line in data.strip().split("\n")
                        if line.strip().startswith(("$", "!"))
                    ]

        except urllib.error.HTTPError as e:
            if e.code >= 500:
                raise FeedTransientError(f"Server error {e.code}: {e.reason}") from e
            elif e.code == 429:
                # Rate limited — extract Retry-After if present
                retry_after = e.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else 30.0
                raise FeedTransientError(f"Rate limited, retry after {wait}s") from e
            elif e.code in (401, 403):
                raise FeedError(f"Authentication failed ({e.code}): check AIS_API_KEY") from e
            else:
                raise FeedTransientError(f"HTTP {e.code}: {e.reason}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FeedTransientError(f"Network error: {e}") from e

    def poll_once(self) -> dict:
        """Execute a single poll cycle. Returns summary stats."""
        if not self._circuit.allow_request():
            logger.debug("Circuit breaker open, skipping poll")
            return {"skipped": True, "reason": "circuit_open"}

        try:
            nmea_lines = self.fetch_nmea_lines()
            self._circuit.record_success()
            self._consecutive_failures = 0

            position_msgs = []
            static_msgs = []

            for line in nmea_lines:
                result = self._parser.process_line(line)
                if result is None:
                    continue
                if isinstance(result, AisStaticData):
                    static_msgs.append(result)
                elif isinstance(result, AisMessage):
                    position_msgs.append(result)

            # Store static data
            for sm in static_msgs:
                self._static_data[sm.mmsi] = sm
                if self.on_static:
                    self.on_static(sm)

            # Run anomaly detection on new position messages
            if position_msgs:
                self._position_buffer.extend(position_msgs)
                # Group by MMSI and run detector per vessel
                by_mmsi: dict[int, list[AisMessage]] = {}
                for msg in position_msgs:
                    by_mmsi.setdefault(msg.mmsi, []).append(msg)

                for mmsi, msgs in by_mmsi.items():
                    anomalies = self._anomaly_detector.scan(msgs)
                    # Filter out spoofed messages
                    clean = [
                        m for m in msgs
                        if not any(
                            a.anomaly_type == "spoofed_signal"
                            and abs((a.timestamp - m.timestamp).total_seconds()) < 60
                            for a in anomalies
                        )
                    ]
                    if clean:
                        # Keep last 500 messages per vessel for track building
                        existing = [m for m in self._position_buffer if m.mmsi == mmsi]
                        if len(existing) > 500:
                            self._position_buffer = [
                                m for m in self._position_buffer if m.mmsi != mmsi
                            ] + existing[-500:]

            # Rebuild tracks from accumulated clean messages
            self._tracks = self._processing.build_tracks(self._position_buffer)

            # Enrich tracks with static data
            for track in self._tracks:
                static = self._static_data.get(track.mmsi)
                if static:
                    track.vessel_name = static.vessel_name or track.vessel_name
                    track.destination = static.destination
                    track.eta = static.eta
                    track.cargo_type = static.cargo_type
                    track.draft_dm = static.draft_dm
                    track.ship_length_m = static.ship_length_m
                    track.ship_breadth_m = static.ship_breadth_m
                    track.last_static_update = static.received_at

            self._last_poll = datetime.now(timezone.utc)

            if self.on_messages:
                self.on_messages(position_msgs)

            return {
                "positions": len(position_msgs),
                "static": len(static_msgs),
                "tracks": len(self._tracks),
                "total_messages": len(self._position_buffer),
                "timestamp": self._last_poll.isoformat(),
            }

        except FeedTransientError as e:
            self._consecutive_failures += 1
            self._circuit.record_failure()
            logger.warning("AIS feed transient error (attempt %d): %s",
                          self._consecutive_failures, e)
            return {"error": str(e), "retry_in": self._backoff()}
        except FeedError as e:
            self._circuit.record_failure()
            logger.error("AIS feed fatal error: %s", e)
            return {"error": str(e), "fatal": True}

    def _backoff(self) -> float:
        """Calculate exponential backoff with jitter."""
        base = self._backoff_base
        exp = min(self._consecutive_failures, 7)  # cap at 128s
        delay = base ** exp
        jitter = random.uniform(0, delay * 0.1)
        return min(delay + jitter, self._backoff_max)

    def get_tracks(self) -> list[VesselTrack]:
        """Get the latest vessel tracks."""
        return self._tracks

    def get_static_data(self, mmsi: int) -> AisStaticData | None:
        """Get static data for a specific vessel."""
        return self._static_data.get(mmsi)

    def get_vessel_name(self, mmsi: int) -> str | None:
        """Get the vessel name from parser cache."""
        return self._parser.get_vessel_name(mmsi)

    def get_all_static_data(self) -> dict[int, AisStaticData]:
        """Get all cached static data."""
        return dict(self._static_data)

    @property
    def last_poll(self) -> datetime | None:
        return self._last_poll

    @property
    def is_healthy(self) -> bool:
        return self._circuit.state == CircuitBreaker.CLOSED

    def start(self) -> None:
        """Start background polling thread."""
        import threading
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("AIS feed client started, polling %s every %.0fs",
                    self.feed_url or "(synthetic)", self.poll_interval)

    def stop(self) -> None:
        """Stop background polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("AIS feed client stopped")

    def _poll_loop(self) -> None:
        """Background loop that polls the AIS feed."""
        while self._running:
            try:
                self.poll_once()
            except Exception as e:
                logger.error("Unexpected error in AIS poll loop: %s", e)
            time.sleep(self.poll_interval)


class FeedError(Exception):
    """Non-retryable feed failure (auth, bad URL, etc.)."""


class FeedTransientError(Exception):
    """Retryable feed failure (timeout, 5xx, network)."""


# ---------------------------------------------------------------------------
# Global singleton (created lazily)
# ---------------------------------------------------------------------------

_feed_client: AisFeedClient | None = None


def get_feed_client() -> AisFeedClient:
    """Get or create the global AIS feed client singleton."""
    global _feed_client
    if _feed_client is None:
        _feed_client = AisFeedClient()
    return _feed_client
