import pytest

from benter_peru.ml.betting import BettingError
from benter_peru.ml.multi_bets import finish_ticket, sequence_ticket


def test_box_covers_mutually_exclusive_orders() -> None:
    weights = {1: 0.4, 2: 0.3, 3: 0.2, 4: 0.1}
    ordered = finish_ticket("Exacta", 1, (1,), weights, (1, 2))
    assert ordered.probability == pytest.approx(0.2)
    box = finish_ticket("Exacta", 1, (1,), weights, (1, 2, 3), box=True)
    assert box.line_count == 6
    assert box.probability == pytest.approx(1 / 3 + 9 / 35 + 7 / 40)


def test_exacton_is_restricted_to_last_race() -> None:
    with pytest.raises(BettingError, match="última"):
        finish_ticket("Exactón", 2, (2, 3), {1: 0.6, 2: 0.4}, (1, 2))


def test_sequence_optimizes_coverage_under_line_limit() -> None:
    ticket = sequence_ticket(
        "Dupleta",
        (1, 2),
        {1: {1: 0.8, 2: 0.2}, 2: {1: 0.55, 2: 0.45}},
        start=1,
        max_lines=2,
        top=2,
    )
    assert ticket.picks == ((1,), (1, 2))
    assert ticket.line_count == 2
    assert ticket.probability == pytest.approx(0.8)
    assert ticket.expected_value is None


def test_full_market_selects_positive_ev_with_actual_per_line_cost() -> None:
    ticket = sequence_ticket(
        "Dupletón",
        (1, 2, 3),
        {2: {1: 0.7, 2: 0.3}, 3: {3: 0.6, 4: 0.4}},
        start=2,
        max_lines=2,
        top=2,
        line_cost=2,
        dividends={(1, 3): 2, (1, 4): 2, (2, 3): 2, (2, 4): 20},
    )
    assert ticket.picks == ((2,), (4,))
    assert ticket.total_cost == 2
    assert ticket.expected_value == pytest.approx(0.2)


def test_sequence_rejects_gaps_and_incorrect_final_window() -> None:
    with pytest.raises(BettingError, match="consecutivas"):
        sequence_ticket("Dupleta", (1, 3), {}, start=1, max_lines=2, top=2)
    with pytest.raises(BettingError, match="últimas"):
        sequence_ticket("Vale de Oro", (1, 2, 3, 4), {}, start=1, max_lines=2, top=2)
