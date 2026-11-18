"""Dependency-free ULID generation for portable 26-character primary keys."""

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """Return a 48-bit millisecond timestamp plus 80 random bits as a ULID."""
    timestamp_ms = time.time_ns() // 1_000_000
    if timestamp_ms >= 1 << 48:
        raise OverflowError("current timestamp does not fit in a ULID")
    value = (timestamp_ms << 80) | int.from_bytes(os.urandom(10), "big")
    encoded = ["0"] * 26
    for index in range(25, -1, -1):
        encoded[index] = _CROCKFORD[value & 31]
        value >>= 5
    return "".join(encoded)
