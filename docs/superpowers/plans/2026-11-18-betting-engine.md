# Betting Engine Implementation Plan

**Status:** COMPLETED — 2026-11-18. All five tasks were implemented through
RED/GREEN/REFACTOR and verified with the complete project suite.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add transparent EV, fractional-Kelly, and ordered Plackett-Luce strategy analysis to the read-only Streamlit dashboard.

**Architecture:** Pure mathematical functions live in `ml/betting.py`; the framework-free UI service maps real predictions and ephemeral quotes into view rows; Streamlit only collects input and renders results. SQLite and model inference remain read-only.

**Tech Stack:** Python 3.12, Streamlit, pandas, Pytest, Ruff, Mypy.

**Spec:** `docs/superpowers/specs/2026-11-18-betting-engine-design.md`

## Global Constraints

- No explicit offered odds means no EV, Kelly, or recommendation.
- Default stake is quarter Kelly (`fraction=0.25`).
- EV less than or equal to zero means zero suggested stake.
- Combination prices are theoretical fair prices, not market recommendations.
- No SQLite write, odds persistence, scraping, or bet placement.

---

### Task 1: Pure EV and Kelly mathematics

**Files:**
- Create: `src/benter_peru/ml/betting.py`
- Create: `tests/ml/test_betting.py`

**Interfaces:**
- Produces: `BettingError`, `calculate_expected_value(...)`, and `calculate_kelly_stake(...)`.

- [ ] Write failing literal, break-even, negative-EV, zero-divisor, non-finite, and invalid-fraction tests.
- [ ] Run `python -m pytest tests/ml/test_betting.py -q` and confirm RED due to the missing module.
- [ ] Implement strict validators, EV, and quarter Kelly.
- [ ] Run focused tests and confirm GREEN.
- [ ] Refactor shared validation while preserving focused GREEN.

### Task 2: Ordered Exacta and Trifecta probabilities

**Files:**
- Modify: `src/benter_peru/ml/betting.py`
- Modify: `tests/ml/test_betting.py`

**Interfaces:**
- Produces: `OrderedCombination` and `generate_top_combinations(...)`.

- [ ] Add failing hand-calculated Exacta/Trifecta, validation, top-N, and deterministic-tie tests.
- [ ] Run the focused tests and confirm RED for the missing combination API.
- [ ] Implement exact permutation enumeration and Plackett-Luce branch products.
- [ ] Sort by `(-joint_probability, participant_ids)` and truncate to `top_n`.
- [ ] Run focused tests, Ruff, and Mypy.

### Task 3: Framework-free strategy composition

**Files:**
- Modify: `src/benter_peru/ui/service.py`
- Create: `tests/ui/test_betting_strategy.py`

**Interfaces:**
- Consumes: `DashboardPrediction`, optional win-odds mapping.
- Produces: `BettingStrategyService`, `WinValueRow`, and `BettingStrategy`.

- [ ] Write failing tests for no quotes, mixed positive/negative EV, name mapping, and combination labels.
- [ ] Run focused tests and confirm RED for the missing service.
- [ ] Implement composition using only explicit odds and pure betting functions.
- [ ] Run focused tests and static checks.

### Task 4: Read-only Streamlit strategy view

**Files:**
- Modify: `src/benter_peru/ui/app.py`
- Create: `tests/ui/test_betting_view.py`

**Interfaces:**
- Consumes: selected race, `PredictionService`, `BettingStrategyService`, and transient `st.data_editor` values.

- [ ] Write failing helper tests that parse nullable positive decimal odds and reject invalid editor values.
- [ ] Implement the new navigation item, editable quote table, action button, refusal state, assessments, and theoretical combination tables.
- [ ] Run focused dashboard tests and static checks.

### Task 5: Simulated Derby fire test and final verification

**Files:**
- Create: `scripts/simulate_betting_strategy.py`
- Create: `tests/integration/test_betting_simulation.py`
- Modify completion status: this plan and its spec.

**Interfaces:**
- Produces: deterministic JSON with assessments, Top-3 Exactas, and Top-3 Trifectas from supplied probabilities and invented quotes.

- [ ] Write a failing integration test for Mr. Peggy and Shotra simulated prices.
- [ ] Implement the script using production strategy functions without duplicating formulas.
- [ ] Run the script and capture the example table/JSON.
- [ ] Run the complete Pytest suite, Ruff, and Mypy.
- [ ] Mark spec and plan implemented, commit on `codex/entregable-9-betting-engine`, and stop for review.
