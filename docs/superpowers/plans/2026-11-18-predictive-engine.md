# Predictive Baseline and Market Engine Implementation Plan

**Implementation status:** COMPLETED — 2026-11-18 (`113 passed`, Ruff and Mypy clean)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train a reproducible synthetic logistic baseline, normalize participant utilities into exact race probabilities, derive exact Plackett–Luce Top-N probabilities, and evaluate optional market prices without presenting the result as calibrated betting advice.

**Architecture:** A pure probability module owns softmax and Plackett–Luce mathematics. `BaselineRaceModel` encodes existing `FeatureVector` values, generates grouped synthetic races, trains a scikit-learn scaling/logistic pipeline, and returns immutable race predictions. A separate market module calculates fair odds and EV only for explicitly supplied decimal prices.

**Tech Stack:** Python 3.12, NumPy 2.x, scikit-learn 1.7+, SQLAlchemy Core, Pytest, Ruff, Mypy.

**Spec:** `docs/superpowers/specs/2026-11-18-predictive-engine.md`

## Global Constraints

- The model is always labeled `synthetic_softmax_baseline`, `calibrated=false`, and `production_ready=false`.
- Training defaults to exactly 500 synthetic races with seven participants and seed `20261118`.
- Participant identity, name, mandil, and input slot are never model features.
- Win probabilities must satisfy `sum(values) == 1.0` exactly.
- Top-N probabilities use exact Plackett–Luce ordered enumeration.
- Market EV uses offered total decimal odds: `probability * odds - 1`.
- Missing odds produce no assessment or recommendation.
- The real fire test emits no wagering recommendation because verified dividends are absent.
- No model artifact, database, PDF, CSV, or generated report is committed.

---

### Task 1: Numerical dependencies

**Files:**

- Modify: `pyproject.toml`

**Interfaces:**

- Provides NumPy arrays and scikit-learn `Pipeline`, `StandardScaler`, and `LogisticRegression`.

- [ ] **Step 1: Record the missing dependency failure**

Run:

```text
python -c "import numpy, sklearn"
```

Expected before implementation: `ModuleNotFoundError: No module named 'numpy'`.

- [ ] **Step 2: Add bounded runtime dependencies**

Add these entries to `[project].dependencies`:

```toml
"numpy>=2.0,<3.0",
"scikit-learn>=1.7,<2.0",
```

- [ ] **Step 3: Install the project development environment**

Run: `python -m pip install -e ".[dev]"`

Expected: installation succeeds and resolves compatible NumPy/scikit-learn versions.

- [ ] **Step 4: Verify imports**

Run: `python -c "import numpy, sklearn; print(numpy.__version__, sklearn.__version__)"`

Expected: NumPy 2.x and scikit-learn 1.7–1.x are printed.

---

### Task 2: Exact probability mathematics

**Files:**

- Create: `src/benter_peru/ml/probabilities.py`
- Create: `tests/ml/test_probabilities.py`

**Interfaces:**

- `stable_softmax(utilities: Mapping[str, float]) -> dict[str, float]`
- `plackett_luce_place_probabilities(strengths: Mapping[str, float], place_positions: int) -> dict[str, float]`
- `ProbabilityError(ValueError)`

- [ ] **Step 1: Write failing softmax tests**

Test three finite utilities and assert all results are positive and `sum(values) == 1.0`.
Reorder the input mapping and assert the participant-to-probability mapping is unchanged.
Test empty IDs, duplicate impossibility at construction boundary, fewer than two runners,
and non-finite utilities.

- [ ] **Step 2: Run and observe RED**

Run: `python -m pytest tests/ml/test_probabilities.py::test_softmax_is_exact_and_permutation_invariant -q`

Expected: import error because `benter_peru.ml.probabilities` does not exist.

- [ ] **Step 3: Implement stable softmax**

Subtract the maximum utility, exponentiate with `math.exp`, divide by the total, and set
the final probability to `1.0 - sum(previous)`. Validate identifiers, runner count, finite
inputs, total, residual, and returned range.

- [ ] **Step 4: Run softmax tests and observe GREEN**

Run the targeted probability tests and require a pass.

- [ ] **Step 5: Write failing Plackett–Luce tests**

Assert:

```python
plackett_luce_place_probabilities(equal_four, 2) == {
    "a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5
}
```

within `1e-12`; assert Top 1 equals win strengths and seven-runner Top 3 sums to 3 within
`1e-12`. Add invalid N, negative, non-finite, and zero-total tests.

- [ ] **Step 6: Run and observe RED**

Expected: Plackett–Luce tests fail because enumeration is absent.

- [ ] **Step 7: Implement recursive ordered enumeration**

At each rank, choose one remaining runner, multiply branch probability by its strength over
remaining total, recurse, and at the terminal rank add the branch probability to every
selected participant. Validate postconditions with `1e-12` tolerance.

- [ ] **Step 8: Run probability tests and observe GREEN**

Run: `python -m pytest tests/ml/test_probabilities.py -q`

Expected: all pure numerical tests pass.

---

### Task 3: Market intelligence

**Files:**

- Create: `src/benter_peru/ml/market.py`
- Create: `tests/ml/test_market.py`

**Interfaces:**

- `fair_odds(probability: float) -> float`
- `expected_value(probability: float, offered_decimal_odds: float) -> float`
- `evaluate_market(...) -> tuple[ValueAssessment, ...]`
- `ValueAssessment` frozen dataclass and `MarketError(ValueError)`

- [ ] **Step 1: Write literal EV tests**

Assert:

```python
fair_odds(0.25) == 4.0
expected_value(0.25, 5.0) == 0.25
expected_value(0.25, 4.0) == 0.0
expected_value(0.25, 3.0) == -0.25
```

Test probability zero/out-of-range/non-finite and odds `<= 1`/non-finite.

- [ ] **Step 2: Run and observe RED**

Run: `python -m pytest tests/ml/test_market.py -q`

Expected: import error because `market.py` does not exist.

- [ ] **Step 3: Implement fair odds and EV**

Use full-precision Python floats and shared validation. Do not round returned values.

- [ ] **Step 4: Add assessment tests**

Supply separate win/place distributions and odds. Assert bet type, fair odds, EV,
`has_value`, deterministic participant/bet ordering, no results when odds are missing, and
`MarketError` for unknown price keys.

- [ ] **Step 5: Implement and verify market assessment**

Only create assessments for supplied odds. Set `has_value = ev > minimum_ev`; validate
that `minimum_ev` is finite.

Run: `python -m pytest tests/ml/test_market.py -q`

Expected: all market tests pass.

---

### Task 4: Synthetic generator and baseline race model

**Files:**

- Create: `src/benter_peru/ml/models.py`
- Modify: `src/benter_peru/ml/__init__.py`
- Create: `tests/ml/test_models.py`

**Interfaces:**

- `SyntheticRaceGenerator.generate(race_count=500, field_size=7) -> SyntheticTrainingSet`
- `BaselineRaceModel.fit_synthetic(race_count=500, field_size=7) -> BaselineRaceModel`
- `BaselineRaceModel.predict_race(participants) -> RacePrediction`
- Frozen `ModelMetadata`, `RacePrediction`, `SyntheticTrainingSet`
- `ModelError`, `ModelNotFittedError`

- [ ] **Step 1: Write failing feature encoder and generator tests**

Construct literal FeatureVectors and assert the encoded column order and `None -> 365.0`
imputation. Generate two datasets with the same seed and assert exact equality, shape
`(3500, 15)` for defaults, 500 group IDs, and exactly one positive label per group.

- [ ] **Step 2: Run and observe RED**

Run: `python -m pytest tests/ml/test_models.py -q`

Expected: import error because `models.py` does not exist.

- [ ] **Step 3: Implement encoder and coherent generator**

Use a local `numpy.random.default_rng(seed)`. Derive subset counts from global starts, rates
from counts plus bounded variation, positive average positions, and deterministic latent
utilities plus Gumbel noise. Return arrays without mutating global random state.

- [ ] **Step 4: Add fit/predict tests**

Assert pre-fit prediction raises `ModelNotFittedError`; after fitting, metadata is exact,
the pipeline contains `StandardScaler` then `LogisticRegression`, every win probability is
positive, their sum equals `1.0`, Top 3 sums to `3.0` within tolerance, and place values are
in range.

- [ ] **Step 5: Implement model fitting and prediction**

Fit a scikit-learn `Pipeline` on flattened synthetic alternatives and binary labels. Use
`decision_function`, `stable_softmax`, and `plackett_luce_place_probabilities` for race
prediction. Preserve participant keys and reject invalid field sizes or duplicate/empty IDs.

- [ ] **Step 6: Add reproducibility and permutation tests**

Fit two models with the same seed and assert predictions match exactly. Reverse participant
input order and assert mappings match by ID within `1e-15` while each returned distribution
still satisfies its conservation rule.

- [ ] **Step 7: Run model tests and observe GREEN**

Run: `python -m pytest tests/ml/test_models.py -q`

Expected: all model tests pass without convergence warnings.

- [ ] **Step 8: Run focused quality checks**

Run: `python -m pytest tests/ml -q`

Run: `python -m ruff check src/benter_peru/ml tests/ml`

Run: `python -m mypy src/benter_peru/ml`

Expected: all commands succeed.

---

### Task 5: Seven-runner real-data fire test and completion

**Files:**

- Modify: `docs/superpowers/specs/2026-11-18-predictive-engine.md` (status only)
- Modify: `docs/superpowers/plans/2026-11-18-predictive-engine.md` (status only)
- Create no repository artifact for the fire-test output.

**Interfaces:**

- Reads the existing real local SQLite database and its meeting 202647 history.
- Prints an ephemeral table and mandatory non-production warning.

- [ ] **Step 1: Run complete automated verification**

Run: `python -m pytest --disable-warnings`

Run: `python -m ruff check .`

Run: `python -m mypy src`

Expected: 81 prior tests plus all new tests pass; Ruff and Mypy are clean.

- [ ] **Step 2: Query and encode the seven real participants**

Order `race_entries` by mandil for meeting `202647`, race `1`. Call `FeatureEngine` for
each horse using date `2026-11-21`, distance `1000`, surface `arena`, and lookback `365`.

- [ ] **Step 3: Train and predict**

Fit `BaselineRaceModel(place_positions=3, random_state=20261118)` with the default 500 x 7
synthetic dataset. Predict all seven participants in one call and display percentages for
win and Top 3.

- [ ] **Step 4: Print mandatory warning**

Print exactly:

```text
BASELINE SINTETICO NO CALIBRADO — production_ready=false.
No se emiten recomendaciones de apuestas reales: no hay dividendos verificados.
```

- [ ] **Step 5: Verify repository hygiene**

Run: `git status --short`

Run: `git ls-files "*.joblib" "*.pkl" "*.csv" "*.db" "*.sqlite" "*.sqlite3"`

Expected: no model or data artifacts are tracked.

- [ ] **Step 6: Mark documents completed and commit**

Set specification and plan status to completed, stage intended files only, and commit:

```text
feat: add synthetic race probabilities and value analysis
```
