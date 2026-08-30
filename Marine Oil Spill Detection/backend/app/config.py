from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve every path relative to THIS file so nothing breaks regardless of the
# process working directory (localhost, scripts, or a container).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/app/config -> project root


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths (relative to project root, resolved above)
    DATA_RAW_DIR: Path = _PROJECT_ROOT / "data" / "raw"
    DATA_PROCESSED_DIR: Path = _PROJECT_ROOT / "data" / "processed"

    # Detection model
    DETECTION_MODEL_WEIGHTS: Path = _PROJECT_ROOT / "backend" / "app" / "models" / "weights"
    DETECTION_THRESHOLD: float = 0.5
    DETECTION_INPUT_SIZE: int = 512
    MODEL_BACKBONE: str = "resnet34"

    # AIS data feed
    AIS_FEED_URL: str = ""                          # HTTP endpoint returning NMEA lines
    AIS_API_KEY: str = ""                           # API key for the AIS provider
    AIS_POLL_INTERVAL_SEC: float = 10.0              # seconds between feed polls
    AIS_REQUEST_TIMEOUT_SEC: float = 30.0            # HTTP request timeout
    AIS_CIRCUIT_BREAKER_THRESHOLD: int = 3           # failures before circuit opens
    AIS_CIRCUIT_BREAKER_RESET_SEC: float = 60.0     # seconds before retry after open
    AIS_FALLBACK_TO_SIMULATION: bool = True          # use simulated data when feed unavailable

    # AIS anomaly detection
    AIS_MAX_SPEED_KNOTS: float = 60.0      # impossible speed threshold
    AIS_MAX_POSITION_JUMP_KM: float = 100.0  # jump between messages
    AIS_SPOOF_SCORE_THRESHOLD: float = 0.7   # 0..1 trust score cutoff

    # Attribution
    ATTRIBUTION_SEARCH_RADIUS_KM: float = 10.0
    ATTRIBUTION_WINDOW_HOURS: float = 6.0

    # API
    API_TITLE: str = "Marine Oil Spill Detection & Attribution API"
    API_VERSION: str = "0.2.0"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Ensure data directories exist
for d in (settings.DATA_RAW_DIR, settings.DATA_PROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)
