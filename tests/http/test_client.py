from collections.abc import Callable

import httpx
import pytest

from benter_peru.http.client import (
    HttpClientConfig,
    ResponsibleHttpClient,
    RetryExhaustedError,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def build_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    config: HttpClientConfig | None = None,
    clock: FakeClock | None = None,
) -> ResponsibleHttpClient:
    fake_clock = clock or FakeClock()
    transport = httpx.MockTransport(handler)
    raw_client = httpx.Client(transport=transport)
    return ResponsibleHttpClient(
        config
        or HttpClientConfig(
            user_agent="BenterPeru/0.1 contacto@example.invalid",
            max_attempts=3,
            base_backoff_seconds=0.25,
            jitter_ratio=0.2,
            min_request_interval_seconds=0.0,
        ),
        client=raw_client,
        sleep=fake_clock.sleep,
        monotonic=fake_clock.monotonic,
        jitter=lambda: 0.0,
    )


def test_retries_server_error_and_preserves_identifiable_user_agent() -> None:
    attempts: list[str] = []
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.headers["User-Agent"])
        status = 500 if len(attempts) == 1 else 200
        return httpx.Response(status, request=request, content=b"ok")

    client = build_client(handler, clock=clock)

    response = client.fetch("https://example.invalid/document.pdf")

    assert response.status_code == 200
    assert response.content == b"ok"
    assert attempts == [
        "BenterPeru/0.1 contacto@example.invalid",
        "BenterPeru/0.1 contacto@example.invalid",
    ]
    assert clock.sleeps == [0.25]


def test_retries_timeout_before_returning_success() -> None:
    attempt_count = 0
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            raise httpx.ReadTimeout("read timed out", request=request)
        return httpx.Response(204, request=request)

    client = build_client(handler, clock=clock)

    response = client.fetch("https://example.invalid/robots.txt")

    assert response.status_code == 204
    assert attempt_count == 2
    assert clock.sleeps == [0.25]


def test_raises_typed_error_after_retryable_status_is_exhausted() -> None:
    attempt_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        return httpx.Response(503, request=request)

    config = HttpClientConfig(
        user_agent="BenterPeru/0.1 contacto@example.invalid",
        max_attempts=2,
        base_backoff_seconds=0.1,
        min_request_interval_seconds=0.0,
    )
    client = build_client(handler, config=config)

    with pytest.raises(RetryExhaustedError) as raised:
        client.fetch("https://example.invalid/unavailable")

    assert raised.value.attempts == 2
    assert raised.value.last_status_code == 503
    assert attempt_count == 2


def test_retry_after_header_takes_priority_over_backoff() -> None:
    attempt_count = 0
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            return httpx.Response(429, request=request, headers={"Retry-After": "3"})
        return httpx.Response(200, request=request)

    client = build_client(handler, clock=clock)

    response = client.fetch("https://example.invalid/rate-limited")

    assert response.status_code == 200
    assert clock.sleeps == [3.0]


def test_spaces_requests_to_the_same_host() -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    config = HttpClientConfig(
        user_agent="BenterPeru/0.1 contacto@example.invalid",
        min_request_interval_seconds=2.0,
    )
    client = build_client(handler, config=config, clock=clock)

    client.fetch("https://example.invalid/first")
    client.fetch("https://example.invalid/second")

    assert clock.sleeps == [2.0]


def test_requires_nonempty_user_agent() -> None:
    with pytest.raises(ValueError, match="user_agent"):
        HttpClientConfig(user_agent="  ")
