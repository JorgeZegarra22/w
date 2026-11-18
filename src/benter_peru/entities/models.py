"""Public entity-resolution result models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolutionReport:
    """Auditable counters for one idempotent resolution request."""

    races_created: int = 0
    races_reused: int = 0
    entries_created: int = 0
    entries_reused: int = 0
    horses_created: int = 0
    horses_reused: int = 0
    jockeys_created: int = 0
    jockeys_reused: int = 0
    trainers_created: int = 0
    trainers_reused: int = 0
    studs_created: int = 0
    studs_reused: int = 0
    unconfirmed_horses: int = 0

