"""Exact race probability mathematics."""

import math

import pytest

from benter_peru.ml.probabilities import (
    ProbabilityError,
    plackett_luce_place_probabilities,
    stable_softmax,
)


def test_softmax_is_exact_and_permutation_invariant() -> None:
    utilities = {"a": 2.5, "b": -0.5, "c": 1.0}

    forward = stable_softmax(utilities)
    reversed_result = stable_softmax(dict(reversed(tuple(utilities.items()))))

    assert all(probability > 0 for probability in forward.values())
    assert sum(forward.values()) == 1.0
    assert sum(reversed_result.values()) == 1.0
    for participant_id in utilities:
        assert forward[participant_id] == pytest.approx(
            reversed_result[participant_id], abs=1e-15
        )


@pytest.mark.parametrize(
    "utilities",
    [
        {"only": 1.0},
        {"": 1.0, "b": 2.0},
        {"a": math.inf, "b": 2.0},
        {"a": math.nan, "b": 2.0},
    ],
)
def test_softmax_rejects_unsafe_inputs(utilities: dict[str, float]) -> None:
    with pytest.raises(ProbabilityError):
        stable_softmax(utilities)


def test_plackett_luce_equal_runners_have_symmetric_top_two_probability() -> None:
    strengths = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}

    result = plackett_luce_place_probabilities(strengths, 2)

    assert result == pytest.approx({key: 0.5 for key in strengths}, abs=1e-12)
    assert sum(result.values()) == pytest.approx(2.0, abs=1e-12)


def test_plackett_luce_top_one_equals_win_strengths() -> None:
    strengths = {"a": 0.5, "b": 0.3, "c": 0.2}

    result = plackett_luce_place_probabilities(strengths, 1)

    assert result == pytest.approx(strengths, abs=1e-12)


def test_plackett_luce_seven_runner_top_three_conserves_three_places() -> None:
    strengths = {f"horse-{index}": index / 28 for index in range(1, 8)}

    result = plackett_luce_place_probabilities(strengths, 3)

    assert all(0 <= probability <= 1 for probability in result.values())
    assert sum(result.values()) == pytest.approx(3.0, abs=1e-12)


@pytest.mark.parametrize(
    ("strengths", "place_positions"),
    [
        ({"a": 0.5, "b": 0.5}, 0),
        ({"a": 0.5, "b": 0.5}, 3),
        ({"a": -0.1, "b": 1.1}, 1),
        ({"a": 0.0, "b": 0.0}, 1),
        ({"a": math.inf, "b": 1.0}, 1),
    ],
)
def test_plackett_luce_rejects_invalid_inputs(
    strengths: dict[str, float], place_positions: int
) -> None:
    with pytest.raises(ProbabilityError):
        plackett_luce_place_probabilities(strengths, place_positions)
