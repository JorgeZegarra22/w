from benter_peru.ml.pace import PaceStyle, classify_pace
from benter_peru.ml.simulator import PaceParticipant, simulate_race


def test_classifier_uses_tactics_and_never_treats_finish_as_a_split() -> None:
    assert (
        classify_pace({"recent_races": [{"comments": "Ganó de punta a punta"}]}).style
        == PaceStyle.PUNTERO
    )
    closer = classify_pace({"recent_races": [{"initial_position": "8º", "position": "2°/10"}]})
    assert closer.style == PaceStyle.CERRADOR and closer.evidence
    fallback = classify_pace({"recent_races": [{"position": "2°/8", "comments": "A ½ cuerpo"}]})
    assert fallback.style == PaceStyle.MEDIO and not fallback.evidence


def test_four_leaders_lose_probability_and_closer_gains_it() -> None:
    field = tuple(
        PaceParticipant(str(n), p, style)
        for n, (p, style) in enumerate(
            (
                (0.30, PaceStyle.PUNTERO),
                (0.20, PaceStyle.PUNTERO),
                (0.15, PaceStyle.PUNTERO),
                (0.10, PaceStyle.PUNTERO),
                (0.25, PaceStyle.CERRADOR),
            )
        )
    )
    adjusted = simulate_race(field, 10_000, seed=42)
    assert sum(adjusted.values()) == 1.0
    assert adjusted["0"] < 0.30
    assert adjusted["4"] > 0.25
    assert adjusted == simulate_race(field, 10_000, seed=42)


def test_two_leaders_do_not_create_a_pace_collision() -> None:
    field = (
        PaceParticipant("a", 0.5, PaceStyle.PUNTERO),
        PaceParticipant("b", 0.25, PaceStyle.PUNTERO),
        PaceParticipant("c", 0.25, PaceStyle.CERRADOR),
    )
    assert simulate_race(field, 10_000) == {"a": 0.5, "b": 0.25, "c": 0.25}


def test_biomechanics_applies_independently_of_pace_collision() -> None:
    field = (
        PaceParticipant("a", 0.4, PaceStyle.PUNTERO, "Fatiga Alta", 18.0),
        PaceParticipant("b", 0.35, PaceStyle.CERRADOR, "Resistencia Alta", -5.0),
        PaceParticipant("c", 0.25, PaceStyle.MEDIO, "Fatiga Moderada", 8.0),
    )
    pace = simulate_race(field, include_biomechanics=False)
    adjusted = simulate_race(field)
    assert pace == {"a": 0.4, "b": 0.35, "c": 0.25}
    assert adjusted["a"] < pace["a"] and adjusted["b"] > pace["b"]
    assert sum(adjusted.values()) == 1.0


def test_trip_adjustment_rewards_cover_and_penalizes_exposure_and_wide_running() -> None:
    field = (
        PaceParticipant("cover", 0.2, PaceStyle.MEDIO, drafting_saved_energy=True),
        PaceParticipant("wide", 0.2, PaceStyle.MEDIO, overground_penalty="Alto"),
        PaceParticipant("wind", 0.2, PaceStyle.PUNTERO, drafting_saved_energy=False),
        PaceParticipant("unknown", 0.2, PaceStyle.PUNTERO),
        PaceParticipant(
            "wide-resistant", 0.2, PaceStyle.MEDIO, "Resistencia Alta", overground_penalty="Alto"
        ),
    )
    assert field[3].trip_energy() == field[4].trip_energy() == 0
    baseline = simulate_race(field, include_trip=False)
    adjusted = simulate_race(field)
    assert adjusted["cover"] > baseline["cover"]
    assert adjusted["wide"] < baseline["wide"]
    assert adjusted["wind"] < baseline["wind"]
    assert sum(adjusted.values()) == 1.0
