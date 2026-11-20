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
