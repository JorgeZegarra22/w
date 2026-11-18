# Entregable 4: Historical Results and Feature Engine Design

**Status:** COMPLETED and ready for final review

**Date:** 2026-11-18

**Scope:** Add an auditable, atomic CSV ingestion path for historical horse-racing
results and calculate leakage-safe, model-ready performance features over a configurable
lookback window. No predictive model is part of this deliverable.

## 1. Goals

- Import structured historical results from a local CSV file.
- Resolve each row to an existing horse without fuzzy matching.
- Roll back the complete file when any row is invalid.
- Preserve file and row provenance with SHA-256 fingerprints.
- Make reimporting the same immutable file idempotent.
- Calculate global, distance-specific, and surface-specific performance features.
- Exclude the target race and all later results from feature calculations.
- Keep schema, constraints, and migrations portable from SQLite to PostgreSQL.

## 2. Non-goals

- No predictive model, training pipeline, ranking, calibration, or betting strategy.
- No historical-results web scraper in this phase.
- No fuzzy horse-name matching or automatic identity correction.
- No speed figures, pace normalization, jockey features, or trainer features.
- No partial CSV imports or persisted failed-import batches.
- No CSV or historical database artifacts committed to Git.

## 3. Chosen Approach

The first supported history adapter is a strict UTF-8 CSV importer implemented with
Python's standard `csv` module. CSV is preferred over JSON because it is easy to inspect,
export, and correct in spreadsheet tools without adding a dataframe dependency. A future
JSON reader may produce the same validated row model without changing persistence or the
Feature Engine.

The CLI contract is:

```text
benter history import --file historial.csv
```

The command uses the configured SQLite path from `BENTER_DATABASE_PATH`, upgrades the
database, imports the file in one `UnitOfWork`, prints a JSON report, and exits nonzero with
an exact row-and-field error when validation fails.

## 4. CSV Contract

### 4.1 Encoding and headers

- Encoding is UTF-8 or UTF-8 with BOM (`utf-8-sig`).
- The first record is a required header row.
- Unknown columns are rejected to catch spelling mistakes.
- Required and optional columns are listed below; column order is irrelevant.
- Blank records are ignored. A record containing some, but not all, required values is an
  error.

| Column | Required | Validation and normalization |
|---|---:|---|
| `horse_id` | Conditional | Existing 26-character ULID; takes absolute identity priority |
| `horse_name` | Conditional | Required when `horse_id` is empty; exact normalized match only |
| `race_date` | Yes | ISO `YYYY-MM-DD` |
| `position` | Yes | Integer greater than zero |
| `distance_meters` | Yes | Integer greater than zero |
| `elapsed_time_seconds` | Yes | Decimal greater than zero, quantized to milliseconds |
| `surface` | Yes | `arena` or `cesped`; accents and case normalized at input |
| `track_condition` | Yes | Non-empty normalized text, maximum 50 characters |
| `meeting_code` | No | Trimmed identifier, maximum 20 characters |
| `race_number` | No | Integer greater than zero when present |

At least one of `horse_id` and `horse_name` must be present.

### 4.2 Horse identity policy

1. When `horse_id` is present, it is the authoritative identifier and must exist in
   `horses`. An unconfirmed horse is allowed through an explicit ID because the caller has
   supplied the exact database identity.
2. When both `horse_id` and `horse_name` are present, the normalized name must match the
   selected horse's `normalized_name`; a contradiction aborts the file.
3. When only `horse_name` is present, apply the Entregable 3 `normalize_name` function and
   require one exact match whose `confirmation_status` is `confirmed`.
4. Never use fuzzy matching. An unknown or unconfirmed name aborts the file.

`horses.normalized_name` is unique at database level, so an exact confirmed lookup cannot
produce multiple rows in the current schema. The importer still treats an unexpected
multiple-row result as an ambiguity error rather than choosing one.

### 4.3 Example

```csv
horse_id,horse_name,race_date,position,distance_meters,elapsed_time_seconds,surface,track_condition,meeting_code,race_number
01M7R000000000000000000001,WAYTT,2026-10-24,1,1000,58.940,arena,seca,202643,3
,REFUGIADO,2026-09-19,3,1000,59.810,arena,humeda,202638,5
```

## 5. Persistence Model

Migration `20261118_0003` revises `20261118_0002` and adds exactly two tables.

### 5.1 `history_import_batches`

| Column | Type | Constraints |
|---|---|---|
| `id` | `String(26)` | Primary key, ULID length check |
| `file_sha256` | `String(64)` | Not null, unique, lowercase SHA-256 length check |
| `source_filename` | `Text` | Not null, basename only |
| `file_format` | `String(20)` | Not null, check equals `csv` |
| `row_count` | `Integer` | Not null, greater than zero |
| `imported_at` | timezone-aware `DateTime` | Not null |

A batch row represents only a completed import. Failed files leave no batch row. An exact
file hash already present returns the prior batch as an idempotent reuse with zero inserts.

### 5.2 `horse_race_results`

| Column | Type | Constraints |
|---|---|---|
| `id` | `String(26)` | Primary key, ULID length check |
| `import_batch_id` | `String(26)` | FK to `history_import_batches`, not null |
| `horse_id` | `String(26)` | FK to `horses`, not null |
| `race_date` | `Date` | Not null |
| `finishing_position` | `Integer` | Not null, greater than zero |
| `distance_meters` | `Integer` | Not null, greater than zero |
| `elapsed_time_seconds` | `Numeric(9, 3)` | Not null, greater than zero |
| `surface` | `String(20)` | Not null, check in `arena`, `cesped` |
| `track_condition` | `String(50)` | Not null, trimmed non-empty check |
| `meeting_code` | `String(20)` | Nullable |
| `race_number` | `Integer` | Nullable, greater than zero when present |
| `row_fingerprint` | `String(64)` | Not null, unique, SHA-256 length check |
| `created_at` | timezone-aware `DateTime` | Not null |

Indexes:

```text
(horse_id, race_date)
(horse_id, distance_meters, race_date)
(horse_id, surface, race_date)
```

The row fingerprint hashes a canonical serialization of horse ID, date, position,
distance, elapsed seconds, surface, track condition, meeting code, and race number. A
duplicate row inside a new file or across a different file is an error and rolls back the
new file. Repeating the identical file is handled first by its batch hash and is a clean
idempotent reuse.

## 6. Atomic History Importer

### 6.1 Components

- `benter_peru.history.models`: validated row and `HistoryImportReport` dataclasses.
- `benter_peru.history.importer.HistoryImporter`: parsing, identity resolution,
  validation, fingerprinting, and persistence.
- `benter_peru.history.errors.HistoryImportError`: stable error carrying row number,
  field name, and reason.
- `benter_peru.cli`: nested `history import --file` command and JSON output.

### 6.2 Transaction flow

1. Read bytes and calculate SHA-256 without modifying storage.
2. Enter one `UnitOfWork`.
3. Return the completed batch when `file_sha256` already exists.
4. Decode and parse the complete CSV inside the transaction boundary.
5. Validate the header and every field, reporting physical CSV row numbers.
6. Resolve every horse under the approved identity policy.
7. Calculate every row fingerprint and reject duplicates.
8. Insert one batch followed by all results.
9. Exit the context and commit only when every operation succeeded.

Any parsing, validation, identity, constraint, or persistence error exits the context with
an exception. `UnitOfWork` rolls back the complete transaction. The CLI renders an error
such as:

```text
HistoryImportError: row 14, horse_name: confirmed horse not found: "tNrzrAMo"
```

The report returned on success is:

```json
{
  "batch_id": "01M7R...",
  "file_sha256": "...",
  "rows_inserted": 24,
  "reused_batch": false
}
```

## 7. Feature Engine

### 7.1 Interface

`src/benter_peru/ml/features.py` exports `FeatureEngine` and `FeatureVector`:

```python
FeatureEngine(engine).for_horse(
    horse_id="01M7R...",
    race_date=date(2026, 11, 21),
    distance_meters=1000,
    surface="arena",
    lookback_days=365,
) -> FeatureVector
```

Inputs are validated: the horse must exist, distance and lookback must be positive, and
surface must be `arena` or `cesped`.

### 7.2 Leakage boundary

Only results satisfying this half-open interval are eligible:

```text
race_date - lookback_days <= result.race_date < race_date
```

The upper bound is strictly less than the target race date. Results on the same date,
future results, and older results are excluded. This rule is applied in SQL before any
aggregate is calculated.

### 7.3 Output and formulas

`FeatureVector` is a typed dictionary with:

| Key | Definition |
|---|---|
| `starts_total` | Count of eligible results |
| `wins_total` | Count whose finishing position is 1 |
| `win_rate` | `wins_total / starts_total` |
| `podium_rate` | Count with position 1–3 divided by `starts_total` |
| `days_since_last_race` | Target date minus latest eligible date; `None` without history |
| `distance_starts` | Eligible starts at requested distance |
| `distance_wins` | Wins at requested distance |
| `distance_win_rate` | Distance wins divided by distance starts |
| `distance_podium_rate` | Distance podiums divided by distance starts |
| `distance_average_position` | Mean finishing position at distance |
| `surface_starts` | Eligible starts on requested surface |
| `surface_wins` | Wins on requested surface |
| `surface_win_rate` | Surface wins divided by surface starts |
| `surface_podium_rate` | Surface podiums divided by surface starts |
| `surface_average_position` | Mean finishing position on surface |

All ratios and averages are rounded to six decimal places. A subgroup with zero starts
returns `0.0` for rates and average position. A horse without eligible history returns zero
for all counts/rates/averages and `None` for `days_since_last_race`.

Elapsed time is retained for future speed-figure work but is intentionally not transformed
into a feature in this deliverable because meaningful comparison requires distance,
surface, and track-condition normalization.

## 8. Error Handling

- File missing or unreadable: CLI error before database mutation.
- Invalid encoding/header/value: `HistoryImportError` with row and field.
- Unknown ID, contradictory ID/name, or unsafe name resolution: rollback.
- Duplicate row fingerprint in a new file: rollback.
- Existing identical file hash: successful idempotent reuse.
- Unknown horse passed to the Feature Engine: `FeatureError`.
- Invalid feature parameters: `FeatureError` before querying aggregates.

Raw CSV lines are never logged. Errors include only the necessary field name, row number,
and offending identity/value.

## 9. TDD and Acceptance Tests

Implementation follows red-green-refactor in this order:

1. Migration table inventory, FKs, checks, unique constraints, and indexes.
2. Valid CSV import using `horse_id` and exact confirmed `horse_name`.
3. ID priority plus rejection of contradictory ID/name.
4. Rejection of unknown and unconfirmed names.
5. Full rollback when a later row is invalid.
6. Same-file idempotency and cross-file duplicate rejection.
7. CLI parsing and JSON report.
8. Global wins, win rate, and podium rate.
9. Distance- and surface-specific metrics.
10. Days since last race.
11. Empty history behavior.
12. Exclusion of same-date, future, and older-than-lookback results.

Acceptance requires:

- All 57 pre-existing tests remain green.
- New importer and Feature Engine tests pass without network access.
- `python -m ruff check .` is clean.
- `python -m mypy src` is clean.
- No CSV, SQLite database, or generated data is tracked by Git.
- Changes are committed only on `codex/entregable-4-history-and-features`.

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Historical names differ from master names | Exact-only lookup fails safely and asks for explicit identity correction |
| Partial or malformed vendor exports | Single transaction and row-specific errors |
| Duplicate races across exports | Unique row fingerprints and same-file hash idempotency |
| Model leakage | Half-open SQL date interval with strict `< target race date` |
| Sparse history produces misleading divisions | Counts accompany rates; zero-denominator convention is explicit |
| SQLite/PostgreSQL divergence | Portable SQLAlchemy types and ordinary checks/indexes only |
