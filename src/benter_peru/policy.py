"""robots.txt policy evaluation for responsible collection."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from benter_peru.http.client import ResponsibleHttpClient, RetryExhaustedError


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Auditable decision derived from a source's robots policy."""

    allowed: bool
    crawl_delay_seconds: float | None
    reason_code: str
    robots_url: str


class PolicyUnavailableError(RuntimeError):
    """Raised when robots policy cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class _Rule:
    path: str
    allowed: bool

    @property
    def specificity(self) -> int:
        return len(self.path.replace("*", "").removesuffix("$"))

    def matches(self, target: str) -> bool:
        anchored = self.path.endswith("$")
        pattern = self.path.removesuffix("$")
        expression = re.escape(pattern).replace(r"\*", ".*")
        if anchored:
            expression += "$"
        return re.match(expression, target) is not None


@dataclass(frozen=True, slots=True)
class _Group:
    user_agents: tuple[str, ...]
    rules: tuple[_Rule, ...]
    crawl_delay: float | None

    def match_specificity(self, user_agent: str) -> int | None:
        matches = [
            0 if candidate == "*" else len(candidate)
            for candidate in self.user_agents
            if candidate == "*" or candidate in user_agent.lower()
        ]
        return max(matches) if matches else None


class PolicyGate:
    """Fetch and evaluate robots.txt using the responsible HTTP client."""

    def __init__(self, client: ResponsibleHttpClient) -> None:
        self._client = client

    def evaluate(self, url: str) -> PolicyDecision:
        robots_url = self._robots_url(url)
        try:
            response = self._client.fetch(robots_url)
        except RetryExhaustedError as exc:
            raise PolicyUnavailableError(f"robots policy unavailable for {robots_url}") from exc

        if response.status_code == 404:
            return PolicyDecision(True, None, "robots_not_found", robots_url)
        if response.status_code in {401, 403}:
            return PolicyDecision(False, None, "robots_access_denied", robots_url)
        if response.status_code != 200:
            raise PolicyUnavailableError(
                f"unexpected robots response {response.status_code} for {robots_url}"
            )

        user_agent = self._client.config.user_agent
        allowed, crawl_delay = self._evaluate_rules(response.text, user_agent, url)

        return PolicyDecision(
            allowed=allowed,
            crawl_delay_seconds=float(crawl_delay) if crawl_delay is not None else None,
            reason_code="robots_allowed" if allowed else "robots_denied",
            robots_url=robots_url,
        )

    @staticmethod
    def _robots_url(url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute HTTP or HTTPS URL")
        return urlunsplit((parsed.scheme.lower(), parsed.netloc, "/robots.txt", "", ""))

    @classmethod
    def _evaluate_rules(
        cls, robots_text: str, user_agent: str, url: str
    ) -> tuple[bool, float | None]:
        groups = cls._parse_groups(robots_text)
        matched = [
            (specificity, group)
            for group in groups
            if (specificity := group.match_specificity(user_agent)) is not None
        ]
        if not matched:
            return True, None

        best_specificity = max(specificity for specificity, _group in matched)
        selected = [group for specificity, group in matched if specificity == best_specificity]
        parsed_url = urlsplit(url)
        target = parsed_url.path or "/"
        if parsed_url.query:
            target = f"{target}?{parsed_url.query}"
        matching_rules = [
            rule for group in selected for rule in group.rules if rule.matches(target)
        ]
        allowed = True
        if matching_rules:
            winning_rule = max(
                matching_rules, key=lambda rule: (rule.specificity, rule.allowed)
            )
            allowed = winning_rule.allowed
        crawl_delay = next(
            (group.crawl_delay for group in selected if group.crawl_delay is not None), None
        )
        return allowed, crawl_delay

    @staticmethod
    def _parse_groups(robots_text: str) -> tuple[_Group, ...]:
        groups: list[_Group] = []
        agents: list[str] = []
        rules: list[_Rule] = []
        crawl_delay: float | None = None
        has_directive = False

        def flush() -> None:
            nonlocal agents, rules, crawl_delay, has_directive
            if agents:
                groups.append(_Group(tuple(agents), tuple(rules), crawl_delay))
            agents = []
            rules = []
            crawl_delay = None
            has_directive = False

        for raw_line in robots_text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if has_directive:
                    flush()
                agents.append(value.lower())
                continue
            if not agents:
                continue
            if field in {"allow", "disallow"}:
                has_directive = True
                if value or field == "allow":
                    rules.append(_Rule(value or "/", field == "allow"))
            elif field == "crawl-delay":
                has_directive = True
                try:
                    parsed_delay = float(value)
                except ValueError:
                    continue
                if parsed_delay >= 0:
                    crawl_delay = parsed_delay

        flush()
        return tuple(groups)
