"""Deterministic narrative grounded in model, snapshots, and explicit quotes."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from benter_peru.ml.betting import BettingError, calculate_expected_value
from benter_peru.ml.multi_bets import Ticket


@dataclass(frozen=True, slots=True)
class AnalystRunner:
    mandil: int
    name: str
    probability: float


def _first_row(profile: Mapping[str, object], key: str) -> dict[object, object]:
    rows = profile.get(key)
    return rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}


def senior_analysis(
    race: int,
    runners: Sequence[AnalystRunner],
    profiles: Mapping[int, Mapping[str, object]],
    offered_odds: Mapping[int, float],
    ticket: Ticket | None = None,
) -> str:
    if not runners:
        raise BettingError("El análisis requiere al menos un participante.")
    ranked = sorted(runners, key=lambda runner: (-runner.probability, runner.mandil))
    favorite = ranked[0]
    sentences = [
        f"Carrera {race}. Favorito del modelo: {favorite.mandil} · {favorite.name} "
        f"({favorite.probability:.1%} de victoria)."
    ]
    profile = profiles.get(favorite.mandil, {})
    form = _first_row(profile, "recent_races")
    workout = _first_row(profile, "workouts")
    if form.get("date") and form.get("position"):
        sentences.append(
            f"Su última actuación registrada fue {form['position']} el {form['date']}."
        )
    if workout.get("date") and workout.get("distance_meters") and workout.get("time"):
        sentences.append(
            f"Su apronte más reciente figura el {workout['date']}: "
            f"{workout['distance_meters']} m en {workout['time']}."
        )
    if not offered_odds:
        sentences.append(
            "Sin cuotas de mercado, el pronóstico expresa una estimación de probabilidad."
        )
    else:
        priced = [
            (calculate_expected_value(item.probability, offered_odds[item.mandil]), item)
            for item in ranked
            if item.mandil in offered_odds
        ]
        if priced and (best := max(priced, key=lambda pair: pair[0]))[0] > 0:
            ev, value = best
            sentences.append(
                f"Apuesta con Valor (+EV): {value.mandil} · {value.name} "
                f"a ganador, con EV estimado de {ev:+.1%}."
            )
        else:
            sentences.append("Las cuotas ingresadas no muestran valor esperado positivo a ganador.")
    if ticket is not None:
        sentences.append(
            f"El boleto {ticket.bet} cubre {ticket.line_count} líneas y "
            f"tiene una probabilidad conjunta estimada de {ticket.probability:.2%}."
        )
    return " ".join(sentences)
