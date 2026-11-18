# History Ingestion and Feature Engine Implementation Plan

**Implementation status:** COMPLETED — 2026-11-18 (`81 passed`, Ruff and Mypy clean)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import auditable historical race results from strict CSV files and calculate leakage-safe horse performance features for a target race.

**Architecture:** Alembic and SQLAlchemy Core add batch and result tables. A `HistoryImporter` parses and validates an entire CSV inside one `UnitOfWork`, resolves horses without fuzzy matching, and persists only complete files. A read-only `FeatureEngine` filters results to a half-open 365-day window and calculates deterministic global, distance, and surface aggregates.

**Tech Stack:** Python 3.12, SQLAlchemy Core 2.x, Alembic, standard-library `csv`, Pytest, Ruff, Mypy.

**Spec:** `docs/superpowers/specs/2026-11-18-history-and-features.md`

## Global Constraints

- Add exactly `history_import_batches` and `horse_race_results` in revision `20261118_0003`.
- Keep all schema constructs portable to PostgreSQL.
- `horse_id` has priority; name-only resolution is exact, normalized, and confirmed-only.
- Never use fuzzy matching in historical imports.
- One invalid row rolls back the complete file.
- Repeating an identical file hash is idempotent.
- Feature history uses `target_date - lookback <= result_date < target_date`.
- No predictive model, scraper, CSV fixture, SQLite database, or generated data is committed.

---

### Task 1: Historical persistence schema

**Files:**

- Modify: `src/benter_peru/db/schema.py`
- Create: `migrations/versions/20261118_0003_history.py`
- Modify: `tests/db/test_schema.py`
- Modify: `tests/db/test_constraints.py`

**Interfaces:**

- Produces tables `history_import_batches` and `horse_race_results` from `benter_peru.db.schema`.
- Produces indexes `ix_horse_results_horse_date`, `ix_horse_results_horse_distance_date`, and `ix_horse_results_horse_surface_date`.

- [ ] **Step 1: Write failing schema inventory and index tests**

Add the two tables to `EXPECTED_TABLES`, these unique constraints:

```python
"history_import_batches": {("file_sha256",)},
"horse_race_results": {("row_fingerprint",)},
```

and this index expectation:

```python
"horse_race_results": {
    "ix_horse_results_horse_date",
    "ix_horse_results_horse_distance_date",
    "ix_horse_results_horse_surface_date",
},
```

- [ ] **Step 2: Run the schema tests and observe RED**

Run: `python -m pytest tests/db/test_schema.py -q`

Expected: table inventory fails because the two historical tables do not exist.

- [ ] **Step 3: Add constraint tests**

Seed a horse, insert one valid batch and result, then assert `IntegrityError` for duplicate
file SHA, duplicate row fingerprint, position zero, distance zero, elapsed time zero,
invalid surface, blank track condition, and race number zero.

- [ ] **Step 4: Implement metadata and migration**

Define the columns, checks, foreign keys, unique constraints, and three composite indexes
exactly as specified. Revision `20261118_0003` must revise `20261118_0002`; downgrade drops
results before batches.

- [ ] **Step 5: Run database tests and observe GREEN**

Run: `python -m pytest tests/db -q`

Expected: all database tests pass.

- [ ] **Step 6: Run static checks for the schema increment**

Run: `python -m ruff check src/benter_peru/db migrations tests/db`

Run: `python -m mypy src/benter_peru/db`

Expected: both commands succeed.

---

### Task 2: Strict atomic CSV importer

**Files:**

- Create: `src/benter_peru/history/__init__.py`
- Create: `src/benter_peru/history/errors.py`
- Create: `src/benter_peru/history/models.py`
- Create: `src/benter_peru/history/importer.py`
- Create: `tests/history/__init__.py`
- Create: `tests/history/test_importer.py`

**Interfaces:**

- `HistoryImporter(engine: Engine).import_csv(path: Path) -> HistoryImportReport`
- `HistoryImportReport(batch_id: str, file_sha256: str, rows_inserted: int, reused_batch: bool)`
- `HistoryImportError(row_number: int | None, field: str, reason: str)`

- [ ] **Step 1: Write the valid-import test**

Create two confirmed horses and a temporary UTF-8 CSV. Identify one row by ID and the
other only by a punctuation/case variant of its exact normalized name. Assert one batch,
two result rows, correct horse IDs, quantized elapsed seconds, and report counters.

- [ ] **Step 2: Run the test and observe RED**

Run: `python -m pytest tests/history/test_importer.py::test_imports_id_and_exact_confirmed_name_atomically -q`

Expected: import error because `benter_peru.history` does not exist.

- [ ] **Step 3: Implement minimal models, errors, parsing, and persistence**

Use `csv.DictReader`, `utf-8-sig`, `Decimal`, `date.fromisoformat`, `normalize_name`,
SHA-256, and `UnitOfWork`. Keep parsing and every database insert inside the same context.
Generate a canonical JSON serialization with sorted keys for each row fingerprint.

- [ ] **Step 4: Run the valid-import test and observe GREEN**

Run the same targeted test and require a pass.

- [ ] **Step 5: Add identity-policy tests**

Add independent tests proving:

- existing `horse_id` selects that row;
- a supplied contradictory name aborts;
- unknown ID aborts;
- name-only unconfirmed horse aborts;
- missing both identifiers aborts.

Each error assertion checks the physical CSV row and field, not private helper behavior.

- [ ] **Step 6: Run identity tests and observe RED**

Run: `python -m pytest tests/history/test_importer.py -q`

Expected: the unimplemented validation branches fail.

- [ ] **Step 7: Implement strict identity validation**

ID lookup is authoritative. When name is also present, compare normalized values. A
name-only lookup filters by `confirmation_status == "confirmed"` and requires exactly one
row. No `best_match` call is permitted.

- [ ] **Step 8: Add atomicity, duplicate, and idempotency tests**

Use a CSV whose first row is valid and second row has an invalid date; after the exception,
assert both history tables are empty. Then test same-file reuse and a different file that
contains an existing row fingerprint.

- [ ] **Step 9: Run those tests and observe RED**

Expected: rollback/idempotency/duplicate branches fail until implemented.

- [ ] **Step 10: Implement complete-file rollback and deduplication**

Look up file hash before parsing. Return the prior batch for an identical hash. Detect
fingerprints already in the database and duplicates within the parsed file before inserts.
Allow all exceptions to escape the `UnitOfWork` so it rolls back.

- [ ] **Step 11: Run importer tests and observe GREEN**

Run: `python -m pytest tests/history/test_importer.py -q`

Expected: all importer tests pass.

---

### Task 3: History CLI

**Files:**

- Modify: `src/benter_peru/cli.py`
- Modify: `tests/test_cli.py`
- Create: `tests/integration/test_cli_history.py`

**Interfaces:**

- Parses `benter history import --file <path>`.
- Prints `HistoryImportReport` as sorted, indented JSON.

- [ ] **Step 1: Write failing nested-parser test**

```python
arguments = build_parser().parse_args(
    ["history", "import", "--file", "history.csv"]
)
assert arguments.command == "history"
assert arguments.history_command == "import"
assert str(arguments.file) == "history.csv"
```

- [ ] **Step 2: Observe RED**

Run: `python -m pytest tests/test_cli.py::test_cli_accepts_history_import -q`

Expected: argparse rejects `history`.

- [ ] **Step 3: Add subparsers and `_import_history`**

Reuse `RuntimeConfig`, `create_database_engine`, and `upgrade_database`; call
`HistoryImporter.import_csv`, serialize `asdict(report)`, and always dispose the engine.

- [ ] **Step 4: Add CLI integration test**

Seed a confirmed horse in the configured temporary database, invoke `main`, parse stdout,
and assert the JSON report plus persisted result. No network adapter is constructed.

- [ ] **Step 5: Run CLI tests and observe GREEN**

Run: `python -m pytest tests/test_cli.py tests/integration/test_cli_history.py -q`

Expected: all pass.

---

### Task 4: Leakage-safe Feature Engine

**Files:**

- Create: `src/benter_peru/ml/__init__.py`
- Create: `src/benter_peru/ml/features.py`
- Create: `tests/ml/__init__.py`
- Create: `tests/ml/test_features.py`

**Interfaces:**

```python
FeatureEngine(engine).for_horse(
    horse_id: str,
    race_date: date,
    distance_meters: int,
    surface: str,
    lookback_days: int = 365,
) -> FeatureVector
```

`FeatureVector` is the 15-key typed dictionary defined in the specification.

- [ ] **Step 1: Write failing aggregate test**

Seed three eligible starts for one horse: positions `1, 1, 3`; two at 1000 m and all on
arena. Assert literal expected values: `wins_total == 2`, `win_rate == 0.666667`,
`podium_rate == 1.0`, distance and surface metrics, and the hand-calculated days since the
latest date.

- [ ] **Step 2: Observe RED**

Run: `python -m pytest tests/ml/test_features.py::test_calculates_global_distance_and_surface_features -q`

Expected: import error because `benter_peru.ml.features` does not exist.

- [ ] **Step 3: Implement validated SQL query and pure aggregation helpers**

Verify horse existence and parameter ranges, query only the half-open date interval, then
calculate counts, rates, means, and last-race days from returned rows. Round calculated
floats to six places.

- [ ] **Step 4: Run aggregate test and observe GREEN**

Run the targeted test and require a pass.

- [ ] **Step 5: Write leakage and empty-history tests**

Seed one older-than-lookback result, one eligible result, one same-date result, and one
future result. Assert only the eligible result contributes. For a second horse without
eligible rows, assert zero counts/rates/averages and `days_since_last_race is None`.

- [ ] **Step 6: Observe RED, implement missing boundaries, then observe GREEN**

Run: `python -m pytest tests/ml/test_features.py -q`

Expected final result: all Feature Engine tests pass.

- [ ] **Step 7: Add invalid-input tests and implementation**

Test unknown horse, zero distance, invalid surface, and zero lookback. Each raises
`FeatureError` before producing a vector.

- [ ] **Step 8: Run focused quality checks**

Run: `python -m pytest tests/ml tests/history tests/integration/test_cli_history.py -q`

Run: `python -m ruff check src/benter_peru/history src/benter_peru/ml tests/history tests/ml`

Run: `python -m mypy src/benter_peru/history src/benter_peru/ml`

Expected: every command succeeds.

---

### Task 5: Synthetic real-database fire test and completion

**Files:**

- Modify: `docs/superpowers/specs/2026-11-18-history-and-features.md` (status only)
- Modify: `docs/superpowers/plans/2026-11-18-history-and-features.md` (status only)
- Create outside repo: `%TEMP%/benter-history-<id>/historial_sintetico.csv`

**Interfaces:**

- Uses the existing real local SQLite database and confirmed horses from meeting 202647.
- Does not commit the CSV, database, or derived output.

- [ ] **Step 1: Run the complete automated verification**

Run: `python -m pytest --disable-warnings`

Run: `python -m ruff check .`

Run: `python -m mypy src`

Expected: 57 prior tests plus all new tests pass; Ruff and Mypy report no issues.

- [ ] **Step 2: Create a temporary synthetic CSV outside the repository**

Use confirmed real horse IDs read from the local database. Include several past results for
WAYTT and at least one result for each other confirmed first-race horse. Do not include the
unconfirmed horse by name. Dates must precede 2026-11-21.

- [ ] **Step 3: Execute the real CLI import once and repeat it**

Set the approved local database and blob environment variables, then run:

```text
benter history import --file <temporary-csv>
```

The first report inserts rows. The second reports `reused_batch=true` and zero inserted.

- [ ] **Step 4: Calculate WAYTT's FeatureVector**

Instantiate `FeatureEngine` against the migrated real database with target date
`2026-11-21`, distance `1000`, surface `arena`, and lookback `365`. Capture the JSON output.

- [ ] **Step 5: Verify repository hygiene**

Run: `git status --short`

Run: `git ls-files "*.csv" "*.db" "*.sqlite" "*.sqlite3"`

Expected: no synthetic data artifacts are tracked and only intended source/docs/tests are
modified.

- [ ] **Step 6: Mark the documents implemented and commit**

Set specification and plan status to completed, stage only intended files, and commit:

```text
feat: ingest history and calculate horse features
```
