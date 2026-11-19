"""Streamlit controls for generating a ticket from one meeting."""

from __future__ import annotations

import streamlit as st

from benter_peru.ml.betting import BettingError
from benter_peru.ml.models import ModelError
from benter_peru.ml.multi_bets import (
    FINISH_RULES,
    SEQUENCE_RULES,
    Ticket,
    finish_ticket,
    sequence_ticket,
    sequence_window,
)
from benter_peru.ml.real_features import HistoricalFeatureError
from benter_peru.ui.queries import DashboardRepository, RaceOption
from benter_peru.ui.service import DashboardPrediction, PredictionService


def _parse_dividends(text: str) -> dict[tuple[int, ...], float]:
    dividends: dict[tuple[int, ...], float] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        picks, _, amount = raw.partition("=")
        try:
            key = tuple(int(pick.strip()) for pick in picks.split("-"))
            value = float(amount.strip().replace(",", "."))
            if key in dividends or any(mandil <= 0 for mandil in key):
                raise ValueError
        except ValueError as error:
            raise BettingError(f"Dividendo inválido o duplicado en línea {number}.") from error
        dividends[key] = value
    return dividends


def _show_ticket(ticket: Ticket, *, box: bool, sale_reference: str) -> None:
    if sale_reference:
        st.success(f"VENTA CONFIRMADA · Referencia declarada por el usuario: {sale_reference}")
    else:
        st.warning("SIMULACIÓN MATEMÁTICA · Disponibilidad en taquilla sin verificar.")
    if ticket.bet in FINISH_RULES:
        picks = "-".join(map(str, ticket.picks[0]))
        st.text(f"Carrera {ticket.races[0]} · {ticket.bet}{' en Box' if box else ''} · {picks}")
    else:
        st.text(
            "\n".join(
                f"Carrera {race}: {'-'.join(map(str, picks))}"
                for race, picks in zip(ticket.races, ticket.picks, strict=True)
            )
        )
        st.caption("La cobertura concatenada supone independencia entre carreras.")
    st.write(f"{ticket.line_count} líneas · Cobertura estimada: {ticket.probability:.2%}")
    if ticket.total_cost is not None:
        st.write(f"Costo total: {ticket.total_cost:.2f}")
    if ticket.expected_value is not None:
        st.write(f"EV estimado por unidad apostada: {ticket.expected_value:+.2%}")
        if ticket.optimized_by_ev:
            st.caption("Selección por EV entre las líneas candidatas cotizadas.")
    else:
        st.caption("Para estimar EV, ingresa costo por línea y dividendos de todas las líneas.")


def show_ticket_generator(
    repository: DashboardRepository,
    prediction_service: PredictionService,
    race: RaceOption,
    prediction: DashboardPrediction,
) -> Ticket | None:
    st.subheader("Generador de Boletos")
    meeting = {
        item.race_number: item
        for item in repository.races_for_meeting(race.meeting_code)
        if item.scheduled_date == race.scheduled_date
    }
    key = f"ticket-{race.id}"
    bet = st.selectbox("Tipo de apuesta", (*FINISH_RULES, *SEQUENCE_RULES), key=f"{key}-bet")
    if bet is None:
        return None
    is_finish = bet in FINISH_RULES
    start = race.race_number
    top = 2
    max_lines = 8
    box = False
    selected: list[int] = []
    if not is_finish:
        starts = []
        for number in meeting:
            try:
                sequence_window(bet, tuple(meeting), number)
            except BettingError:
                continue
            starts.append(number)
        if not starts:
            st.info("La reunión seleccionada no contiene la ventana requerida.")
            return None
        chosen = st.selectbox("Carrera inicial", starts, key=f"{key}-start-{bet}")
        if chosen is None:
            return None
        start = chosen
    elif bet == "Exactón" and race.race_number != max(meeting, default=0):
        st.info("El Exactón se juega en la última carrera de la reunión.")
        return None

    with st.form(f"{key}-form-{bet}"):
        if is_finish:
            rows = sorted(prediction.rows, key=lambda row: (-row.win_probability, row.mandil))
            names = {row.mandil: row.horse_name for row in rows}
            selected = st.multiselect(
                "Mandiles en orden de llegada (o todos los del Box)",
                tuple(names),
                default=list(names)[: FINISH_RULES[bet]],
                format_func=lambda mandil: f"{mandil} · {names[mandil]}",
            )
            box = st.checkbox("En Box")
        else:
            top = st.radio("Candidatos por carrera", (2, 3), horizontal=True)
            max_lines = int(st.number_input("Límite de líneas", 1, 729, value=8, step=1))
            if bet == "Cuádruple":
                st.caption(
                    "Boleto de cuatro ganadores. Canje y Reenganche se confirman en taquilla."
                )
        cost = st.number_input("Costo por línea (opcional)", min_value=0.01, value=None)
        prices = st.text_area(
            "Dividendos brutos por línea (opcional)",
            help="Un importe por línea, en la misma moneda que el costo. Ejemplo: 1-2=20.50",
        )
        sale_reference = st.text_input(
            "Referencia de venta verificada (opcional)",
            help="Ingresa el programa o confirmación de taquilla para este tipo y ventana.",
        ).strip()
        submitted = st.form_submit_button("Generar boleto")
    if not submitted:
        return None

    try:
        dividends = _parse_dividends(prices)
        if is_finish:
            ticket = finish_ticket(
                bet,
                race.race_number,
                tuple(meeting),
                {row.mandil: row.win_probability for row in prediction.rows},
                selected,
                box=box,
                line_cost=cost,
                dividends=dividends,
            )
        else:
            probabilities = {}
            for number in sequence_window(bet, tuple(meeting), start):
                leg = meeting[number]
                projected = (
                    prediction
                    if leg.id == race.id
                    else prediction_service.for_race(
                        leg,
                        repository.participants_for_race(leg.id),
                    )
                )
                probabilities[number] = {row.mandil: row.win_probability for row in projected.rows}
            ticket = sequence_ticket(
                bet,
                tuple(meeting),
                probabilities,
                start=start,
                max_lines=max_lines,
                top=top,
                line_cost=cost,
                dividends=dividends,
            )
    except (BettingError, HistoricalFeatureError, ModelError) as error:
        st.error(f"No se pudo generar el boleto. {error}")
        return None
    _show_ticket(ticket, box=box, sale_reference=sale_reference)
    return ticket
