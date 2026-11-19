"""Auditable expected-value, Kelly, and ordered-combination mathematics."""

import math

import pytest

from benter_peru.ml.betting import (
    BettingError,
    calculate_expected_value,
    calculate_kelly_stake,
    generate_top_combinations,
)


def test_expected_value_uses_total_decimal_odds() -> None:
    assert calculate_expected_value(0.25, 5.0) == 0.25
    assert calculate_expected_value(0.25, 4.0) == 0.0
    assert calculate_expected_value(0.25, 3.0) == -0.25


def test_quarter_kelly_is_zero_without_positive_value() -> None:
    assert calculate_kelly_stake(0.25, 5.0) == pytest.approx(0.015625)
    assert calculate_kelly_stake(0.25, 4.0) == 0.0
    assert calculate_kelly_stake(0.25, 3.0) == 0.0


@pytest.mark.parametrize("probability", [0.0, -0.1, 1.1, math.inf, math.nan])
def test_invalid_probability_fails_closed(probability: float) -> None:
    with pytest.raises(BettingError, match="probability"):
        calculate_expected_value(probability, 3.0)


@pytest.mark.parametrize("offered_odds", [1.0, 0.0, -1.0, math.inf, math.nan])
def test_zero_divisor_or_invalid_decimal_odds_fail_closed(
    offered_odds: float,
) -> None:
    with pytest.raises(BettingError, match="odds"):
        calculate_kelly_stake(0.4, offered_odds)


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.1, math.inf, math.nan])
def test_invalid_kelly_fraction_fails_closed(fraction: float) -> None:
    with pytest.raises(BettingError, match="fraction"):
        calculate_kelly_stake(0.4, 3.0, fraction=fraction)


def test_exacta_uses_exact_ordered_plackett_luce_probability() -> None:
    combinations = generate_top_combinations(
        {"a": 0.5, "b": 0.3, "c": 0.2}, bet_type="exacta", top_n=3
    )

    assert [item.participant_ids for item in combinations] == [
        ("a", "b"),
        ("b", "a"),
        ("a", "c"),
    ]
    assert combinations[0].joint_probability == pytest.approx(0.3)
    assert combinations[1].joint_probability == pytest.approx(3 / 14)
    assert combinations[2].joint_probability == pytest.approx(0.2)
    assert combinations[0].fair_odds == pytest.approx(10 / 3)


def test_trifecta_uses_all_three_ordered_branches() -> None:
    combinations = generate_top_combinations(
        {"a": 0.5, "b": 0.3, "c": 0.2}, bet_type="trifecta", top_n=2
    )

    assert [item.participant_ids for item in combinations] == [
        ("a", "b", "c"),
        ("b", "a", "c"),
    ]
    assert combinations[0].joint_probability == pytest.approx(0.3)
    assert combinations[1].joint_probability == pytest.approx(3 / 14)


def test_combination_ties_have_deterministic_participant_order() -> None:
    combinations = generate_top_combinations(
        {"c": 1.0, "a": 1.0, "b": 1.0}, bet_type="exacta", top_n=3
    )

    assert [item.participant_ids for item in combinations] == [
        ("a", "b"),
        ("a", "c"),
        ("b", "a"),
    ]
    assert all(item.joint_probability == pytest.approx(1 / 6) for item in combinations)


@pytest.mark.parametrize(
    ("probabilities", "bet_type", "top_n"),
    [
        ({"a": 0.5, "b": 0.5}, "trifecta", 3),
        ({"a": 0.5, "b": 0.0}, "exacta", 3),
        ({"a": 0.5, "b": math.inf}, "exacta", 3),
        ({"a": 0.5, "b": 0.5}, "quinela", 3),
        ({"a": 0.5, "b": 0.5}, "exacta", 0),
    ],
)
def test_invalid_combination_inputs_fail_closed(
    probabilities: dict[str, float], bet_type: str, top_n: int
) -> None:
    with pytest.raises(BettingError):
        generate_top_combinations(
            probabilities,
            bet_type=bet_type,  # type: ignore[arg-type]
            top_n=top_n,
        )
