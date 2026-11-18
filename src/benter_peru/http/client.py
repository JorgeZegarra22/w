"""Synchronous HTTP client with pacing and deterministic retry policy."""

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True, slots=True)
class HttpClientConfig:
    """Configuration for responsible network access."""

    user_agent: str
    timeout_seconds: float = 10.0
    max_attempts: int = 4
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 30.0
    jitter_ratio: float = 0.25
    min_request_interval_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("user_agent must be nonempty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.base_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("backoff values must be nonnegative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")
        if self.min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must be nonnegative")


class RetryExhaustedError(RuntimeError):
    """Raised after all attempts for a retryable failure are consumed."""

    def __init__(
        self,
        *,
        url: str,
        attempts: int,
        response: httpx.Response | None = None,
        cause: httpx.TimeoutException | None = None,
    ) -> None:
        self.url = url
        self.attempts = attempts
        self.response = response
        self.cause = cause
        status = response.status_code if response is not None else None
        detail = f"status {status}" if status is not None else type(cause).__name__
        super().__init__(f"retryable request failed after {attempts} attempts: {detail}")

    @property
    def last_status_code(self) -> int | None:
        return self.response.status_code if self.response is not None else None


class ResponsibleHttpClient:
    """HTTPX adapter with per-host pacing and retry behavior."""

    def __init__(
        self,
        config: HttpClientConfig,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=config.timeout_seconds, trust_env=False)
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._last_request_started_at: dict[str, float] = {}
        self._pacing_lock = Lock()

    def fetch(
        self, url: str, *, headers: Mapping[str, str] | None = None
    ) -> httpx.Response:
        """Fetch a URL, retrying timeouts, 429 responses, and all 5xx responses."""
        request_headers = dict(headers or {})
        request_headers["User-Agent"] = self.config.user_agent

        for attempt in range(1, self.config.max_attempts + 1):
            self._pace(url)
            try:
                response = self._client.get(
                    url,
                    headers=request_headers,
                    timeout=self.config.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if attempt == self.config.max_attempts:
                    raise RetryExhaustedError(
                        url=url, attempts=attempt, cause=exc
                    ) from exc
                self._sleep(self._backoff_seconds(attempt))
                continue

            if not self._is_retryable_status(response.status_code):
                response.extensions["benter_attempt_count"] = attempt
                return response
            if attempt == self.config.max_attempts:
                raise RetryExhaustedError(
                    url=url, attempts=attempt, response=response
                )
            self._sleep(self._retry_delay(response, attempt))

        raise AssertionError("retry loop must return or raise")

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code <= 599

    def _backoff_seconds(self, attempt: int) -> float:
        exponential = min(
            self.config.base_backoff_seconds * (2.0 ** (attempt - 1)),
            self.config.max_backoff_seconds,
        )
        return exponential + exponential * self.config.jitter_ratio * self._jitter()

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                parsed = float(retry_after)
            except ValueError:
                pass
            else:
                if parsed >= 0:
                    return parsed
        return self._backoff_seconds(attempt)

    def _pace(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        with self._pacing_lock:
            now = self._monotonic()
            previous = self._last_request_started_at.get(host)
            if previous is not None:
                remaining = self.config.min_request_interval_seconds - (now - previous)
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._monotonic()
            self._last_request_started_at[host] = now
