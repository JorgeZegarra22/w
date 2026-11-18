"""Environment-backed configuration for reproducible source runs."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

_CONTACT_PATTERN = re.compile(r"\(\+https?://[^)]+\)")


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    source_url: str
    user_agent: str
    database_path: Path
    blob_root: Path
    min_request_interval_seconds: float = 2.0
    http_max_attempts: int = 4
    review_confidence_threshold: float = 0.8

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path.resolve().as_posix()}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RuntimeConfig":
        values = os.environ if env is None else env
        source_url = values.get("BENTER_SOURCE_URL", "").strip()
        if urlsplit(source_url).scheme not in {"http", "https"}:
            raise ValueError("BENTER_SOURCE_URL must be an absolute HTTP or HTTPS URL")

        user_agent = values.get("BENTER_USER_AGENT", "").strip()
        if _CONTACT_PATTERN.search(user_agent) is None:
            raise ValueError("BENTER_USER_AGENT must include a contact URL in '(+https://...)'")

        database_value = values.get("BENTER_DATABASE_PATH", "").strip()
        blob_value = values.get("BENTER_BLOB_ROOT", "").strip()
        if not database_value or not blob_value:
            raise ValueError("BENTER_DATABASE_PATH and BENTER_BLOB_ROOT are required")

        interval = cls._interval_seconds(values)
        attempts = int(values.get("BENTER_HTTP_MAX_ATTEMPTS", "4"))
        threshold = float(values.get("BENTER_REVIEW_CONFIDENCE_THRESHOLD", "0.80"))
        if interval < 0:
            raise ValueError("request interval must be nonnegative")
        if attempts < 1:
            raise ValueError("BENTER_HTTP_MAX_ATTEMPTS must be at least one")
        if not 0 <= threshold <= 1:
            raise ValueError("BENTER_REVIEW_CONFIDENCE_THRESHOLD must be between zero and one")

        return cls(
            source_url=source_url,
            user_agent=user_agent,
            database_path=Path(database_value).expanduser(),
            blob_root=Path(blob_value).expanduser(),
            min_request_interval_seconds=interval,
            http_max_attempts=attempts,
            review_confidence_threshold=threshold,
        )

    @staticmethod
    def _interval_seconds(values: Mapping[str, str]) -> float:
        seconds = values.get("BENTER_MIN_REQUEST_INTERVAL_SECONDS")
        if seconds is not None:
            return float(seconds)
        milliseconds = values.get("BENTER_MIN_REQUEST_INTERVAL_MS", "2000")
        return float(milliseconds) / 1000.0
