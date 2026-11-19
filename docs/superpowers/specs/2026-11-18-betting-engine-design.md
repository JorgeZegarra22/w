# Betting Engine Design

**Status:** Implemented and verified
**Date:** 2026-11-18
**Target branch:** `codex/entregable-9-betting-engine`

## 1. Objective

Convert race-normalized model probabilities into auditable market analysis without
inventing prices or presenting theoretical combinations as actionable bets. The
dashboard accepts decimal win odds only as ephemeral user input. No quote or
strategy result is persisted.

## 2. Safety Policy

- An offered decimal price must be explicitly entered by the user.
- Missing odds produce no EV, Kelly stake, or bet recommendation.
- A non-positive EV always produces a zero stake.
- Exacta and Trifecta outputs are probability rankings and fair prices only;
  without combination-market prices they are not value recommendations.
- The default stake is quarter Kelly (`fraction=0.25`).
- Invalid, infinite, or ambiguous numerical inputs fail closed.

## 3. Pure Betting API

`src/benter_peru/ml/betting.py` exposes:

```python
def calculate_expected_value(probability: float, offered_odds: float) -> float: ...

def calculate_kelly_stake(
    probability: float,
    offered_odds: float,
    fraction: float = 0.25,
) -> float: ...

def generate_top_combinations(
    race_probabilities: Mapping[str, float],
    bet_type: Literal["exacta", "trifecta"] = "exacta",
    top_n: int = 3,
) -> tuple[OrderedCombination, ...]: ...
```

EV uses total decimal odds:

```text
EV = probability * offered_odds - 1
```

Kelly uses net odds `b = offered_odds - 1` and loss probability `q = 1-p`:

```text
full_kelly = (b*p - q) / b
fractional_kelly = max(0, fraction * full_kelly)
```

`probability` must be finite and in `(0, 1]`; decimal odds must be finite and
greater than `1`; `fraction` must be finite and in `(0, 1]`. These constraints
remove division by zero and prevent negative or leveraged stake outputs.

## 4. Ordered Combinations

The generator requires at least two runners for Exacta and three for Trifecta.
All strengths must be finite and positive. They are normalized internally, so
the API is safe for either probabilities or proportional strengths.

For an ordered selection `(i1, i2, ..., ik)`, Plackett-Luce probability is:

```text
P(order) = product(strength(selected) / strength(remaining field))
```

Every permutation of length two or three is enumerated exactly. Results sort by
descending probability and then lexicographically by participant IDs, providing
deterministic ties. `OrderedCombination` contains bet type, ordered participant
IDs, joint probability, and fair decimal odds `1 / probability`.

## 5. Strategy Composition

The framework-free dashboard service receives a real-model prediction plus an
optional mapping of participant IDs to user-entered win odds. It returns:

- the existing runner probability rows;
- zero or more `WinValueAssessment` rows;
- the top three Exactas;
- the top three Trifectas.

Only entered odds are assessed. Positive EV rows may be described as having
value; all other rows carry zero suggested bankroll. Combination outputs never
carry `has_value` because no offered combination dividend exists.

## 6. Streamlit View

The sidebar adds `Estrategia de Apuestas`. The view selects any registered race,
calculates its real-model probabilities, and displays:

1. A `st.data_editor` table with Mandil, Caballo, Probabilidad, Cuota Justa, and
   an editable nullable `Cuota Real` column.
2. An `Analizar Valor` button.
3. If no valid quote is entered, an informational refusal to recommend.
4. Otherwise, an assessment table with EV and quarter-Kelly bankroll percentage.
5. Separate Top-3 Exacta and Top-3 Trifecta tables, explicitly labeled as
   theoretical probabilities and fair prices.

The editor is transient Streamlit state. SQLite remains read-only.

## 7. Testing

- Literal EV and quarter-Kelly examples.
- Zero stake for break-even and negative EV.
- Zero-divisor odds (`<=1`), invalid probabilities, invalid fractions, NaN, and
  infinity fail closed.
- Exacta and Trifecta probabilities match hand-calculated Plackett-Luce values.
- Ties sort deterministically.
- Missing odds produce no assessments.
- Dashboard strategy composition maps participant IDs back to names and never
  promotes fair prices to offered prices.
- Existing real-model, ingestion, and read-only dashboard tests remain green.

## 8. Non-Goals

- Persisting odds or strategies.
- Scraping tote prices.
- Calculating Exacta/Trifecta EV without actual combination prices.
- Automated bet placement.
- Extracting `Estudie su Polla` in this deliverable.
