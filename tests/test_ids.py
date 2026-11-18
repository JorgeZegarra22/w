"""Tests for portable ULID identifiers."""

import re

from benter_peru.ids import new_ulid


def test_new_ulid_has_database_compatible_shape() -> None:
    generated = new_ulid()

    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", generated)
    assert generated != new_ulid()
