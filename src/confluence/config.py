"""Central configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class UtilitySpec:
    name: str
    unit: str
    freq: str          # canonical (normalised) sampling frequency
    raw_freq_note: str


UTILITIES: dict[str, UtilitySpec] = {
    "electricity": UtilitySpec("electricity", "kWh", "15min", "fixed 15-minute interval"),
    "gas": UtilitySpec("gas", "m3", "1h", "fixed hourly interval"),
    "water": UtilitySpec("water", "L/min", "15min", "irregular 5-30 minute interval"),
}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env(
        "DATABASE_URL", "postgresql://confluence:confluence@localhost:5432/confluence"))
    kafka_bootstrap: str = field(default_factory=lambda: _env("KAFKA_BOOTSTRAP", "localhost:9092"))
    raw_topic: str = field(default_factory=lambda: _env("KAFKA_RAW_TOPIC", "meter-readings-raw"))
    alert_topic: str = field(default_factory=lambda: _env("KAFKA_ALERT_TOPIC", "anomaly-alerts"))
    artifacts_dir: Path = field(default_factory=lambda: Path(_env("ARTIFACTS_DIR", str(ROOT / "artifacts"))))
    reports_dir: Path = field(default_factory=lambda: Path(_env("REPORTS_DIR", str(ROOT / "reports"))))
    replay_speed: float = field(default_factory=lambda: float(_env("REPLAY_SPEED", "600")))
    latency_target_s: float = 2.5
    data_mode: str = field(default_factory=lambda: _env("DATA_MODE", "auto"))   # auto | demo | database
    api_key: str = field(default_factory=lambda: _env("API_KEY", ""))           # empty = open (local demo)
    seed: int = field(default_factory=lambda: int(_env("SEED", "42")))


settings = Settings()
