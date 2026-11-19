"""Render official programs while enforcing each source's robots rules."""

from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic, sleep
from urllib.parse import urlsplit

from playwright.sync_api import Error, Page, Route, TimeoutError, sync_playwright

from benter_peru.http.client import HttpClientConfig, ResponsibleHttpClient
from benter_peru.policy import PolicyGate
from benter_peru.scrapers.official_scraper import MEETING_URL, OFFICIAL_HOST, OfficialProgramError

PROVIDER_HOST = "eltiaback.elturf.com"
_BLOCKED_TYPES = {"image", "media", "font", "websocket", "ping"}


@contextmanager
def official_page(user_agent: str, *, channel: str | None = None) -> Iterator[Page]:
    http = ResponsibleHttpClient(
        HttpClientConfig(user_agent=user_agent, min_request_interval_seconds=2.5)
    )
    gate = PolicyGate(http)
    policies: dict[str, tuple[str, float]] = {}
    for url in (MEETING_URL, f"https://{PROVIDER_HOST}/"):
        decision = gate.evaluate(url)
        if not decision.allowed:
            raise OfficialProgramError(f"robots.txt denegó {url}")
        robots = ""
        if decision.reason_code != "robots_not_found":
            response = http.fetch(decision.robots_url)
            if response.status_code != 200:
                raise OfficialProgramError(f"política inestable para {url}")
            robots = response.text
        policies[urlsplit(url).netloc] = (robots, max(2.5, decision.crawl_delay_seconds or 0.0))

    last: dict[str, float] = {}
    blocked_status: list[int] = []

    def route_request(route: Route) -> None:
        request = route.request
        target = urlsplit(request.url)
        host = target.netloc
        policy = policies.get(host)
        if (
            target.scheme != "https"
            or policy is None
            or blocked_status
            or request.method not in {"GET", "OPTIONS"}
            or request.resource_type in _BLOCKED_TYPES
            or (host == PROVIDER_HOST and request.resource_type not in {"fetch", "xhr"})
        ):
            route.abort()
            return
        robots, interval = policy
        allowed, delay = gate._evaluate_rules(robots, user_agent, request.url)
        if not allowed:
            route.abort()
            return
        interval = max(interval, delay or 0.0)
        if request.resource_type in {"document", "fetch", "xhr"}:
            now = monotonic()
            sleep(max(0.0, last.get(host, now - interval) + interval - now))
            last[host] = monotonic()
        try:
            response = route.fetch(max_redirects=0, max_retries=0, timeout=12000)
        except Error:
            route.abort()
            return
        if response.status in {401, 403, 429} or response.headers.get("cf-mitigated"):
            blocked_status.append(response.status)
        if response.status in {301, 302, 303, 307, 308} or blocked_status:
            route.abort()
        else:
            route.fulfill(response=response)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=channel, headless=True)
        try:
            context = browser.new_context(user_agent=user_agent, service_workers="block")
            context.route("**/*", route_request)
            try:
                yield context.new_page()
            finally:
                context.unroute_all(behavior="wait")
                context.close()
        finally:
            browser.close()
    if blocked_status:
        raise OfficialProgramError(f"el origen rechazó la navegación: {blocked_status[0]}")


def render_program(page: Page, url: str, *, meeting: bool = False) -> str:
    if urlsplit(url).netloc != OFFICIAL_HOST:
        raise OfficialProgramError("URL fuera del sitio oficial")
    response = page.goto(url, wait_until="domcontentloaded", timeout=40000)
    if response is None or response.status != 200:
        raise OfficialProgramError(f"la vista oficial no devolvió HTTP 200: {url}")
    selector = "a[href*='programa?carrera=']" if meeting else "div.border-2.rounded-lg table"
    ready = page.locator(selector).first
    if meeting:
        ready = ready.or_(page.get_by_text("Todavía no hay programación oficial", exact=True))
    else:
        ready = ready.or_(page.get_by_text("No se pudo cargar el programa de la carrera."))
    try:
        ready.first.wait_for(state="attached", timeout=32000)
    except TimeoutError as error:
        raise OfficialProgramError(f"la vista oficial no terminó de cargar: {url}") from error
    return page.content()
