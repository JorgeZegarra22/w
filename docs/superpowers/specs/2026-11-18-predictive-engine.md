# Entregable 5: Synthetic Predictive and Market Intelligence Engine

**Status:** Approved design; pending written-spec review

**Date:** 2026-11-18

**Scope:** Add a deterministic, explicitly synthetic baseline that converts horse feature
vectors into race-normalized win probabilities, derives configurable Top-N place
probabilities with the exact Plackett–Luce ordering model, and evaluates value only when
decimal market odds are supplied. The model is not calibrated for real wagering.

## 1. Goals

- Train a reproducible reference model with 500 synthetic seven-runner races.
- Use scikit-learn `StandardScaler` and `LogisticRegression` to learn participant utility.
- Convert participant utilities to one race-level softmax distribution.
- Guarantee the returned win probabilities sum to exactly `1.0` in Python arithmetic.
- Derive exact Top-N place probabilities with Plackett–Luce enumeration.
- Calculate fair odds and expected value from optional offered decimal odds.
- Produce a seven-runner fire-test table from meeting 202647, race 1.
- Label every prediction as synthetic, uncalibrated, and not production-ready.

## 2. Non-goals

- No claim that the probabilities are empirically calibrated or profitable.
- No real-money recommendation without supplied market odds.
- No LightGBM, neural network, ensemble, hyperparameter search, or AutoML.
- No persistence or deployment of a serialized model artifact.
- No model registry, online endpoint, user interface, bankroll sizing, or Kelly staking.
- No use of same-race outcomes or future information in Feature Engine inputs.
- No attempt to infer missing market dividends from fair odds.

## 3. Mathematical Model

### 3.1 Participant utility

Every participant contributes the same ordered numerical representation of the 15-key
`FeatureVector`. `days_since_last_race=None` is deterministically imputed to `365.0` before
scaling. Counts, rates, recency, and average-position fields are retained; no horse name,
mandil, row order, or identity is included as a numerical predictor.

The scikit-learn pipeline is:

```text
FeatureVector rows
    -> StandardScaler
    -> LogisticRegression(solver="lbfgs", max_iter=1000, random_state=20261118)
```

Each training row has a binary label: `1` for the winner of its synthetic race and `0` for
the other runners. The learned `decision_function` is used as a common participant utility.
The binary sigmoid probabilities are not returned and are never normalized. For a target
race, utilities are normalized jointly by softmax:

```text
z_i = utility_i - max(utility)
p_i = exp(z_i) / sum_j(exp(z_j))
```

This construction is permutation-invariant, accepts fields of different sizes, and is a
race-normalized logistic/softmax baseline. It is not described as a fitted conditional
choice model because its binary loss is an approximation used only for bootstrap plumbing.

To guarantee exact normalization after ordinary floating-point operations, probabilities
are calculated in participant input order and the final value is set to:

```text
1.0 - sum(all_previous_probabilities)
```

The implementation validates that this residual is finite and nonnegative. At least two
participants are required, participant IDs must be unique and non-empty, and every encoded
feature must be finite.

### 3.2 Synthetic bootstrap data

`SyntheticRaceGenerator(random_state=20261118)` creates exactly 500 races with seven
participants each by default. It uses NumPy's local `Generator`, never global random state.

For each participant it generates internally coherent feature values:

- nonnegative start and win counts;
- rates in `[0, 1]`;
- average positions greater than or equal to `1` when starts exist;
- recency in `[5, 365]` or `None` for sparse histories;
- distance and surface subsets no larger than global starts.

A documented latent utility rewards win/podium rates and penalizes worse average position
and long inactivity. Independent Gumbel noise is added and exactly one runner per race is
labeled winner using `argmax`. The generator returns flattened feature rows, binary labels,
and race-group IDs so tests can verify one winner per race even though scikit-learn trains
on the flattened rows.

The synthetic formula exists only to create a learnable reference signal. It is not a
domain truth, and the coefficients it induces must not be interpreted as validated racing
effects.

## 4. Public Model Contracts

`src/benter_peru/ml/models.py` exports:

```python
class BaselineRaceModel:
    def __init__(
        self,
        *,
        place_positions: int = 3,
        random_state: int = 20261118,
    ) -> None: ...

    def fit_synthetic(
        self,
        *,
        race_count: int = 500,
        field_size: int = 7,
    ) -> BaselineRaceModel: ...

    def predict_race(
        self,
        participants: Mapping[str, FeatureVector],
    ) -> RacePrediction: ...
```

`RacePrediction` is an immutable dataclass containing:

```python
win_probabilities: dict[str, float]
place_probabilities: dict[str, float]
metadata: ModelMetadata
```

`ModelMetadata` contains exactly:

```python
model_type = "synthetic_softmax_baseline"
training_data = "synthetic"
random_state: int
race_count: int
field_size: int
place_positions: int
production_ready = False
calibrated = False
```

Calling `predict_race` before fitting raises `ModelNotFittedError`. A prediction requires
`1 <= place_positions <= participant_count`.

## 5. Exact Plackett–Luce Place Probabilities

`plackett_luce_place_probabilities` consumes positive win-strength values normalized to
one and an integer `place_positions`.

For an ordered Top-N tuple `(i_1, ..., i_N)`:

```text
P(i_1, ..., i_N) = product over r=1..N of
    strength(i_r) / sum(strength of runners not selected before r)
```

The implementation recursively enumerates all ordered selections of length N and adds each
order probability to every runner included in that order. For seven runners and Top 3 this
is `7 * 6 * 5 = 210` terminal orders.

Postconditions:

- every place probability is finite and in `[0, 1]` within a `1e-12` tolerance;
- the place probabilities sum to `place_positions` within `1e-12`;
- Top 1 equals the win distribution within `1e-12`;
- four equal runners with Top 2 each receive `0.5`.

Invalid N, duplicate/empty participant IDs, non-finite values, negative values, zero total
strength, or fewer than two runners raise `ProbabilityError`.

## 6. Market Intelligence

`src/benter_peru/ml/market.py` exports:

```python
def fair_odds(probability: float) -> float: ...

def expected_value(
    probability: float,
    offered_decimal_odds: float,
) -> float: ...

def evaluate_market(
    *,
    win_probabilities: Mapping[str, float],
    place_probabilities: Mapping[str, float],
    win_odds: Mapping[str, float] | None = None,
    place_odds: Mapping[str, float] | None = None,
    minimum_ev: float = 0.0,
) -> tuple[ValueAssessment, ...]: ...
```

Definitions:

```text
fair_odds = 1 / estimated_probability
expected_value = estimated_probability * offered_decimal_odds - 1
has_value = expected_value > minimum_ev
```

`offered_decimal_odds` means total decimal return including stake and must be finite and
strictly greater than `1.0`. Estimated probabilities must be finite and in `(0, 1]`.
Expected values and fair odds are not rounded internally; presentation may round copies.

`ValueAssessment` contains participant ID, bet type (`win` or `place`), estimated
probability, fair odds, offered decimal odds, expected value, minimum EV, and `has_value`.
Only participants with supplied odds are assessed. Missing win/place maps produce no
assessment for that market; unknown odds keys raise `MarketError` instead of being silently
ignored. No odds means an empty tuple, not a recommendation.

## 7. Dependencies

Add runtime dependencies:

```toml
"numpy>=2.0,<3.0"
"scikit-learn>=1.7,<2.0"
```

The model does not pass the deprecated `multi_class` parameter. The `lbfgs` solver and
pipeline preprocessing are compatible with the approved scikit-learn range. Tests may use
NumPy arrays only through public model contracts; production code preserves ordinary
Python dictionaries at its external boundary.

## 8. Fire Test

The fire test uses the real local SQLite database but writes no model or report artifact:

1. Migrate the database to head.
2. Query meeting `202647`, race `1`, ordered by mandil.
3. For each race entry, call `FeatureEngine.for_horse` with target date `2026-11-21`,
   distance `1000`, surface `arena`, and lookback `365`.
4. Fit `BaselineRaceModel(place_positions=3, random_state=20261118)` on 500 synthetic
   seven-runner races.
5. Predict win and Top-3 probabilities for all seven participants in one call.
6. Print name, confirmation status, win probability, and Top-3 probability.
7. Print the complete `ModelMetadata` warning.
8. Do not call `evaluate_market` because the source data contains no verified offered
   dividends.

The table is illustrative output from synthetic training. It must include this warning:

```text
BASELINE SINTETICO NO CALIBRADO — production_ready=false.
No se emiten recomendaciones de apuestas reales: no hay dividendos verificados.
```

## 9. TDD and Acceptance Tests

Implementation follows red-green-refactor in this order:

1. FeatureVector encoding, deterministic imputation, and finite-value validation.
2. Synthetic generator dimensions, one winner per race, coherence, and reproducibility.
3. Fit-state validation and deterministic model training.
4. Race softmax positivity, permutation invariance, and exact `sum == 1.0`.
5. Plackett–Luce Top 1 identity, equal-runner Top 2, and Top 3 total.
6. Plackett–Luce invalid inputs.
7. Fair odds and positive, zero, and negative EV literals.
8. Market assessment with optional/missing odds and unknown participants.
9. Seven-participant integration from Feature Engine to prediction.
10. Real local fire test and explicit non-production warning.

Acceptance requires:

- All 81 pre-existing tests remain green.
- New tests prove win probabilities sum exactly to `1.0` using `==`, not tolerance.
- New tests prove place probabilities sum to N within `1e-12`.
- Synthetic training and predictions reproduce exactly for the same seed.
- `python -m ruff check .` is clean.
- `python -m mypy src` is clean.
- No serialized model, CSV, database, PDF, or generated report is tracked by Git.
- Changes are committed only on `codex/entregable-5-predictive-engine`.

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Synthetic probabilities mistaken for forecasts | Metadata and mandatory warning mark them uncalibrated and non-production |
| Binary training loss confused with conditional likelihood | Specification labels it an approximation; softmax is applied only at race prediction |
| Participant-order bias | Same encoder/model for each runner; no mandil or slot feature; permutation test |
| Numerical overflow | Maximum-shifted softmax and finite-value checks |
| Place probability approximated incorrectly | Exact Plackett–Luce order enumeration with symmetry and conservation tests |
| “Fair odds” used as market dividend | Separate `fair_odds` and `offered_decimal_odds` names and types |
| Betting advice emitted without price data | Missing odds return no assessments; fire test carries explicit warning |
| Future leakage | Fire test obtains features exclusively from the existing half-open Feature Engine window |
