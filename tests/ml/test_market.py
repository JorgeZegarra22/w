"""Market value calculations use explicit decimal prices."""

import math

import pytest

from benter_peru.ml.market import (
    MarketError,
    evaluate_market,
    expected_value,
    fair_odds,
)


def test_fair_odds_and_expected_value_have_literal_results() -> None:
    assert fair_odds(0.25) == 4.0
    assert expected_value(0.25, 5.0) == 0.25
    assert expected_value(0.25, 4.0) == 0.0
    assert expected_value(0.25, 3.0) == -0.25


@pytest.mark.parametrize("probability", [0.0, -0.1, 1.1, math.inf, math.nan])
def test_probability_validation_rejects_unsafe_values(probability: float) -> None:
    with pytest.raises(MarketError):
        fair_odds(probability)


@pytest.mark.parametrize("odds", [1.0, 0.0, -2.0, math.inf, math.nan])
def test_decimal_odds_must_exceed_one(odds: float) -> None:
    with pytest.raises(MarketError):
        expected_value(0.25, odds)


def test_market_assessment_reports_win_and_place_value() -> None:
    assessments = evaluate_market(
        win_probabilities={"a": 0.4, "b": 0.6},
        place_probabilities={"a": 0.7, "b": 0.9},
        win_odds={"a": 3.0},
        place_odds={"b": 1.5},
        minimum_ev=0.05,
    )

    assert [(item.participant_id, item.bet_type) for item in assessments] == [
        ("a", "win"),
        ("b", "place"),
    ]
    assert assessments[0].fair_odds == 2.5
    assert assessments[0].expected_value == pytest.approx(0.2)
    assert assessments[0].has_value is True
    assert assessments[1].expected_value == pytest.approx(0.35)


def test_missing_odds_produce_no_assessments() -> None:
    assert (
        evaluate_market(
            win_probabilities={"a": 0.4, "b": 0.6},
            place_probabilities={"a": 0.7, "b": 0.9},
        )
        == ()
    )


def test_unknown_odds_participant_is_rejected() -> None:
    with pytest.raises(MarketError, match="unknown participant"):
        evaluate_market(
            win_probabilities={"a": 0.4, "b": 0.6},
            place_probabilities={"a": 0.7, "b": 0.9},
            win_odds={"missing": 4.0},
        )
