"""Official ticket rules and joint probabilities for model-based simulations."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import permutations, product

from benter_peru.ml.betting import BettingError

FINISH_RULES: Mapping[str, int] = {"Exacta": 2, "Exactón": 2, "Trifecta": 3, "Cuatrifecta": 4}
SEQUENCE_RULES: Mapping[str, int] = {
    "Dupleta": 2,
    "Dupletón": 2,
    "Vale Triple": 3,
    "Vale de Oro": 3,
    "Cuádruple": 4,
    "Pick 6": 6,
}
_FINALS = {"Dupletón", "Vale de Oro"}


@dataclass(frozen=True, slots=True)
class TicketLine:
    numbers: tuple[int, ...]
    probability: float


@dataclass(frozen=True, slots=True)
class Ticket:
    bet: str
    races: tuple[int, ...]
    picks: tuple[tuple[int, ...], ...]
    lines: tuple[TicketLine, ...]
    total_cost: float | None = None
    expected_value: float | None = None  # net return per unit staked
    optimized_by_ev: bool = False

    @property
    def probability(self) -> float:
        return min(1.0, math.fsum(line.probability for line in self.lines))

    @property
    def line_count(self) -> int:
        return len(self.lines)


def _weights(probabilities: Mapping[int, float]) -> dict[int, float]:
    if not probabilities or any(
        number <= 0 or not math.isfinite(p) or not 0 < p <= 1 for number, p in probabilities.items()
    ):
        raise BettingError("Se necesitan mandiles positivos y probabilidades finitas en (0, 1].")
    total = math.fsum(probabilities.values())
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise BettingError("Las probabilidades de cada carrera deben sumar 1.")
    return {number: p / total for number, p in probabilities.items()}


def _finish_probability(weights: Mapping[int, float], order: Sequence[int]) -> float:
    remaining = dict(weights)
    joint = 1.0
    for number in order:
        total = math.fsum(remaining.values())
        joint *= remaining.pop(number) / total
    return joint


def _meeting(races: Sequence[int]) -> tuple[int, ...]:
    if not races or len(races) != len(set(races)) or min(races) <= 0:
        raise BettingError("La reunión requiere números de carrera únicos y positivos.")
    return tuple(sorted(races))


def sequence_window(bet: str, races: Sequence[int], start: int) -> tuple[int, ...]:
    length = SEQUENCE_RULES.get(bet)
    if length is None:
        raise BettingError("Tipo de apuesta concatenada desconocido.")
    available = _meeting(races)
    window = tuple(range(start, start + length))
    if bet in _FINALS and window != available[-length:]:
        raise BettingError(f"{bet} se juega en las {length} últimas carreras de la reunión.")
    if not set(window).issubset(available):
        raise BettingError(f"{bet} requiere {length} carreras consecutivas de la misma reunión.")
    return window


def _validate_market(line_cost: float | None, dividends: Mapping[tuple[int, ...], float]) -> None:
    if line_cost is not None and (not math.isfinite(line_cost) or line_cost <= 0):
        raise BettingError("El costo por línea debe ser finito y positivo.")
    if any(not math.isfinite(value) or value < 0 for value in dividends.values()):
        raise BettingError("Los dividendos brutos deben ser finitos y no negativos.")


def _ticket(
    bet: str,
    races: tuple[int, ...],
    picks: tuple[tuple[int, ...], ...],
    lines: tuple[TicketLine, ...],
    line_cost: float | None,
    dividends: Mapping[tuple[int, ...], float],
    *,
    optimized: bool = False,
) -> Ticket:
    _validate_market(line_cost, dividends)
    cost = None if line_cost is None else len(lines) * line_cost
    ev = None
    if cost is not None and all(line.numbers in dividends for line in lines):
        expected_return = math.fsum(line.probability * dividends[line.numbers] for line in lines)
        ev = expected_return / cost - 1
    return Ticket(bet, races, picks, lines, cost, ev, optimized)


def finish_ticket(
    bet: str,
    race: int,
    meeting_races: Sequence[int],
    probabilities: Mapping[int, float],
    numbers: Sequence[int],
    *,
    box: bool = False,
    line_cost: float | None = None,
    dividends: Mapping[tuple[int, ...], float] | None = None,
) -> Ticket:
    length = FINISH_RULES.get(bet)
    if length is None:
        raise BettingError("Tipo de apuesta de llegada desconocido.")
    available = _meeting(meeting_races)
    if race not in available or (bet == "Exactón" and race != available[-1]):
        raise BettingError(
            "El Exactón se juega en la última carrera de la reunión."
            if bet == "Exactón"
            else "La carrera no pertenece a la reunión."
        )
    weights = _weights(probabilities)
    selected = tuple(numbers)
    if len(set(selected)) != len(selected) or not set(selected).issubset(weights):
        raise BettingError("Selecciona mandiles distintos e inscritos en esta carrera.")
    if len(selected) < length or (not box and len(selected) != length):
        raise BettingError(f"{bet} requiere {length} mandiles en orden o al menos {length} en Box.")
    orders = permutations(selected, length) if box else iter((selected,))
    lines = tuple(TicketLine(order, _finish_probability(weights, order)) for order in orders)
    return _ticket(bet, (race,), (selected,), lines, line_cost, dividends or {})


def sequence_ticket(
    bet: str,
    meeting_races: Sequence[int],
    probabilities: Mapping[int, Mapping[int, float]],
    *,
    start: int,
    max_lines: int,
    top: int,
    line_cost: float | None = None,
    dividends: Mapping[tuple[int, ...], float] | None = None,
) -> Ticket:
    """Maximize coverage within the line budget or ROI with every candidate priced."""
    window = sequence_window(bet, meeting_races, start)
    if top not in (2, 3) or max_lines < 1:
        raise BettingError("Usa Top 2 o Top 3 y un límite positivo de líneas.")
    if not set(window).issubset(probabilities):
        raise BettingError("Faltan probabilidades del modelo para la ventana seleccionada.")
    market = dividends or {}
    _validate_market(line_cost, market)
    weights = tuple(_weights(probabilities[race]) for race in window)
    candidates = tuple(
        tuple(sorted(race, key=lambda number: (-race[number], number))[:top]) for race in weights
    )

    def line(order: tuple[int, ...]) -> TicketLine:
        return TicketLine(order, math.prod(p[n] for p, n in zip(weights, order, strict=True)))

    if line_cost is not None and market and all(order in market for order in product(*candidates)):
        # ROI on equally priced lines is the mean of the individual ROIs.
        best = min(
            (line(order) for order in product(*candidates)),
            key=lambda item: (
                -item.probability * market[item.numbers],
                -item.probability,
                item.numbers,
            ),
        )
        picks: tuple[tuple[int, ...], ...] = tuple((number,) for number in best.numbers)
        return _ticket(bet, window, picks, (best,), line_cost, market, optimized=True)

    best_score: tuple[float, int] = (-1.0, 0)
    best_picks: tuple[tuple[int, ...], ...] = ()
    sizes = (range(1, len(leg) + 1) for leg in candidates)
    for counts in product(*sizes):
        count = math.prod(counts)
        if count > max_lines:
            continue
        picks = tuple(leg[:n] for leg, n in zip(candidates, counts, strict=True))
        coverage = math.prod(
            math.fsum(p[number] for number in leg) for p, leg in zip(weights, picks, strict=True)
        )
        if (coverage, -count) > best_score:
            best_score = coverage, -count
            best_picks = picks
    lines = tuple(line(order) for order in product(*best_picks))
    return _ticket(bet, window, best_picks, lines, line_cost, market)
