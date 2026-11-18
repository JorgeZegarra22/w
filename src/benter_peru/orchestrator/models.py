"""Public orchestration result models."""

from dataclasses import dataclass
from typing import Literal

type RunStatus = Literal[
    "completed",
    "completed_with_reviews",
    "partial_failure",
    "deferred",
    "failed",
]


@dataclass(frozen=True, slots=True)
class RunResult:
    crawl_run_id: str
    status: RunStatus
    discovered_count: int
    downloaded_count: int
    deduplicated_count: int
    fact_count: int
    review_count: int
    failure_count: int
