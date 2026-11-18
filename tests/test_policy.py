import httpx

from benter_peru.http.client import HttpClientConfig, ResponsibleHttpClient
from benter_peru.policy import PolicyGate

ROBOTS = """User-agent: *
Disallow: /private
Allow: /private/public
Crawl-delay: 7
"""


def build_policy_gate(response_status: int = 200) -> tuple[PolicyGate, list[str]]:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(response_status, request=request, text=ROBOTS)

    raw_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ResponsibleHttpClient(
        HttpClientConfig(
            user_agent="BenterPeru/0.1 contacto@example.invalid",
            min_request_interval_seconds=0.0,
        ),
        client=raw_client,
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
    )
    return PolicyGate(client), requested_urls


def test_policy_gate_denies_disallowed_url_and_returns_crawl_delay() -> None:
    gate, requested_urls = build_policy_gate()

    decision = gate.evaluate("https://example.invalid/private/program.pdf")

    assert decision.allowed is False
    assert decision.crawl_delay_seconds == 7.0
    assert decision.reason_code == "robots_denied"
    assert decision.robots_url == "https://example.invalid/robots.txt"
    assert requested_urls == ["https://example.invalid/robots.txt"]


def test_policy_gate_honors_explicit_allow_rule() -> None:
    gate, _requested_urls = build_policy_gate()

    decision = gate.evaluate("https://example.invalid/private/public/program.pdf")

    assert decision.allowed is True
    assert decision.crawl_delay_seconds == 7.0
    assert decision.reason_code == "robots_allowed"


def test_missing_robots_file_allows_access_without_delay() -> None:
    gate, _requested_urls = build_policy_gate(response_status=404)

    decision = gate.evaluate("https://example.invalid/program.pdf")

    assert decision.allowed is True
    assert decision.crawl_delay_seconds is None
    assert decision.reason_code == "robots_not_found"


def test_forbidden_robots_file_fails_closed() -> None:
    gate, _requested_urls = build_policy_gate(response_status=403)

    decision = gate.evaluate("https://example.invalid/program.pdf")

    assert decision.allowed is False
    assert decision.reason_code == "robots_access_denied"
