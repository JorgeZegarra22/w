"""Pure normalization and conservative fuzzy matching tests."""

from benter_peru.entities.normalization import best_match, normalize_name


def test_punctuation_case_and_spacing_normalize_to_one_jockey() -> None:
    assert normalize_name("J H SUAREZ") == "j h suarez"
    assert normalize_name("  J.  H. Suarez ") == "j h suarez"


def test_unique_candidate_above_threshold_is_returned() -> None:
    match = best_match(
        "j h suarex",
        {"jockey-1": "j h suarez", "jockey-2": "g a rojas"},
        threshold=0.90,
    )

    assert match is not None
    assert match.entity_id == "jockey-1"
    assert match.score >= 0.90


def test_candidate_below_threshold_is_not_returned() -> None:
    assert best_match("waytt", {"horse-1": "refugiado"}, threshold=0.98) is None


def test_tied_best_candidates_are_ambiguous() -> None:
    assert best_match(
        "abcz",
        {"entity-1": "abcx", "entity-2": "abcy"},
        threshold=0.70,
    ) is None
