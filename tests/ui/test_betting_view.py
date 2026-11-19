"""Transient dashboard market-quote parsing tests."""

import math

import pandas as pd  # type: ignore[import-untyped]
import pytest

from benter_peru.ml.betting import BettingError
from benter_peru.ui.app import _parse_offered_odds


def test_nullable_editor_quotes_are_omitted_without_fabricating_prices() -> None:
    frame = pd.DataFrame.from_records(
        [
            {"participant_id": "horse-a", "Cuota Real": 3.5},
            {"participant_id": "horse-b", "Cuota Real": None},
        ]
    )

    assert _parse_offered_odds(frame) == {"horse-a": 3.5}


@pytest.mark.parametrize("value", [1.0, 0.0, -2.0, math.inf, "texto"])
def test_invalid_editor_quote_fails_closed(value: object) -> None:
    frame = pd.DataFrame.from_records(
        [{"participant_id": "horse-a", "Cuota Real": value}]
    )

    with pytest.raises(BettingError, match="Cuota Real"):
        _parse_offered_odds(frame)
