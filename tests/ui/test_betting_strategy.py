"""Framework-free betting strategy composition tests."""

import pytest

from benter_peru.ml.betting import BettingError
from benter_peru.ui.service import (
    BettingStrategyService,
    DashboardPrediction,
    PredictionRow,
)


def _prediction() -> DashboardPrediction:
    return DashboardPrediction(
        rows=(
            PredictionRow("horse-a", 1, "ALPHA", 0.5, 0.9, 2.0),
            PredictionRow("horse-b", 2, "BETA", 0.3, 0.7, 10 / 3),
            PredictionRow("horse-c", 3, "GAMMA", 0.2, 0.4, 5.0),
        ),
        provenance="real model",
        training_rows=31_418,
    )


def test_missing_quotes_produce_no_value_assessments() -> None:
    strategy = BettingStrategyService().analyze(_prediction(), {})

    assert strategy.win_assessments == ()
    assert strategy.has_market_quotes is False
    assert [item.horse_names for item in strategy.exactas] == [
        ("ALPHA", "BETA"),
        ("BETA", "ALPHA"),
        ("ALPHA", "GAMMA"),
    ]
    assert len(strategy.trifectas) == 3


def test_only_explicit_quotes_are_assessed_and_negative_value_stakes_zero() -> None:
    strategy = BettingStrategyService().analyze(
        _prediction(), {"horse-a": 2.5, "horse-c": 4.0}
    )

    assert [item.horse_name for item in strategy.win_assessments] == [
        "ALPHA",
        "GAMMA",
    ]
    alpha, gamma = strategy.win_assessments
    assert alpha.expected_value == pytest.approx(0.25)
    assert alpha.kelly_stake == pytest.approx(1 / 24)
    assert alpha.has_value is True
    assert gamma.expected_value == pytest.approx(-0.2)
    assert gamma.kelly_stake == 0.0
    assert gamma.has_value is False


def test_quote_for_unknown_runner_fails_closed() -> None:
    with pytest.raises(BettingError, match="unknown participant"):
        BettingStrategyService().analyze(_prediction(), {"missing": 4.0})
