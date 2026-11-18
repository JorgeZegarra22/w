# Entity Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reprocess the approved race program with extractor version 3, resolve its structured facts into six portable master/race tables, and expose an idempotent `benter resolve --sha` command.

**Architecture:** SQLAlchemy Core metadata and Alembic add the six approved tables. The extractor emits one `race_context` and structured `race_entry` facts; an `EntityResolver` loads the completed version 3 extraction and resolves all entities inside one `UnitOfWork` transaction using exact normalization first and conservative `difflib` fallback.

**Tech Stack:** Python 3.12, SQLAlchemy Core 2.x, Alembic, SQLite, `pdfplumber`, `difflib`, Pytest, Ruff, Mypy.

**Spec:** `docs/superpowers/specs/2026-11-18-entity-resolution-design.md`

## Global Constraints

- Add exactly six application tables: `horses`, `jockeys`, `trainers`, `studs`, `races`, and `race_entries`.
- Keep schema types and migrations portable to PostgreSQL.
- Use extractor name `pdfplumber-hipico-text`, version `3`, and a versioned SHA-256 input fingerprint.
- Preserve noisy source text exactly; never correct `tNrzrAMo (usA)` automatically.
- Disable horse fuzzy matching when `horse_requires_review` or the source fact review flag is true.
- Use fuzzy thresholds `0.98` for confirmed horses and `0.94` for jockeys, trainers, and studs.
- Make extraction and resolution independently idempotent.
- Keep the real PDF, blob directory, and SQLite database outside Git.

---

### Task 1: Portable entity schema and migration

**Files:**

- Modify: `src/benter_peru/db/schema.py`
- Create: `migrations/versions/20261118_0002_entities.py`
- Modify: `tests/db/test_schema.py`
- Modify: `tests/db/test_constraints.py`

**Interfaces:**

- Produces SQLAlchemy tables `horses`, `jockeys`, `trainers`, `studs`, `races`, and `race_entries` exported from `benter_peru.db.schema`.
- Migration revision `20261118_0002` revises `20261118_0001` and supports upgrade and downgrade.

- [ ] **Step 1: Extend the failing table inventory and uniqueness contract**

Add all six table names to `EXPECTED_TABLES`, then require these unique sets:

```python
"horses": {("normalized_name",)},
"jockeys": {("normalized_name",)},
"trainers": {("normalized_name",)},
"studs": {("normalized_name",)},
"races": {("meeting_code", "race_number")},
"race_entries": {("source_fact_id",), ("race_id", "mandil")},
```

Add behavior tests proving duplicate normalized names, duplicate race identity, duplicate race/mandil, invalid status, non-positive distance, and non-positive mandil fail with `IntegrityError`.

- [ ] **Step 2: Run the database tests and verify RED**

Run: `python -m pytest tests/db -q`

Expected: inventory and constraint tests fail because the six tables do not exist.

- [ ] **Step 3: Define the six SQLAlchemy Core tables**

Implement the exact columns, named foreign keys, named unique constraints, and checks from the approved specification. Reuse `_ulid`; use `Date`, `DateTime(timezone=True)`, `Numeric(5, 2)`, and portable strings.

- [ ] **Step 4: Create Alembic revision `20261118_0002`**

Create master tables first, then `races`, then `race_entries`; downgrade in reverse order. Use named constraints matching metadata.

- [ ] **Step 5: Run GREEN verification**

Run: `python -m pytest tests/db -q`

Expected: all database tests pass with 26 application tables.

---

### Task 2: Extractor version 3, stud, and race context

**Files:**

- Create: `src/benter_peru/extraction/identity.py`
- Modify: `src/benter_peru/extraction/hipico_table.py`
- Modify: `src/benter_peru/extraction/pdf_text.py`
- Modify: `src/benter_peru/orchestrator/run.py`
- Modify: `tests/extraction/test_hipico_table.py`
- Modify: `tests/integration/test_cli_local_flow.py`

**Interfaces:**

- `EXTRACTOR_NAME = "pdfplumber-hipico-text"`
- `EXTRACTOR_VERSION = "3"`
- `HipicoTableExtractor.extract(...) -> tuple[StructuredFact, ...]` returns one `race_context` followed by first-race `race_entry` facts.
- Every entry JSON includes `stud` and `horse_requires_review`.

- [ ] **Step 1: Add failing synthetic extraction assertions**

Extend the synthetic page header with:

```text
REUNION 202647
PROGRAMA PARA LAS CARRERAS DEL SABADO 21 DE NOVIEMBRE 2026
1ra. CAR.- HANDICAP DISTANCIA 1,000 METROS ARENA
```

Assert one context fact with meeting `202647`, date `2026-11-21`, race `1`, distance `1000`, surface `arena`. Assert entry stud `S.B.P.` and `horse_requires_review` values.

- [ ] **Step 2: Run extractor tests and verify RED**

Run: `python -m pytest tests/extraction/test_hipico_table.py -q`

Expected: missing `race_context`, `stud`, and `horse_requires_review` assertions fail.

- [ ] **Step 3: Implement version identity and extraction**

Read stud words from page-width band `0.435 <= x0 < 0.56`. Parse context from page-1 text with tolerant meeting/date/distance/surface expressions. Emit no partial context fact when any required field is absent.

- [ ] **Step 4: Replace orchestration literals with version constants**

Compute the input fingerprint from `blob_sha256`, `EXTRACTOR_NAME`, and `EXTRACTOR_VERSION`; persist the same constants in `extraction_runs`.

- [ ] **Step 5: Run extractor and local-flow GREEN verification**

Run: `python -m pytest tests/extraction tests/integration/test_cli_local_flow.py -q`

Expected: context, stud, noise preservation, bbox, persistence, and local idempotency tests pass.

---

### Task 3: Name normalization and conservative matching

**Files:**

- Create: `src/benter_peru/entities/__init__.py`
- Create: `src/benter_peru/entities/normalization.py`
- Create: `tests/entities/__init__.py`
- Create: `tests/entities/test_normalization.py`

**Interfaces:**

- `normalize_name(value: str) -> str`
- `best_match(observed: str, candidates: Mapping[str, str], threshold: float) -> Match | None`
- `Match(entity_id: str, score: float)`

- [ ] **Step 1: Write normalization and matching tests**

Assert:

```python
assert normalize_name("J H SUAREZ") == "j h suarez"
assert normalize_name("J. H. Suarez") == "j h suarez"
```

Test one above-threshold unique match, one below-threshold result, and one tied-best result returning `None`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/entities/test_normalization.py -q`

Expected: import fails because the entities package does not exist.

- [ ] **Step 3: Implement normalization and `difflib.SequenceMatcher` matching**

Use NFKD, remove combining marks, replace non-alphanumeric characters with spaces, case-fold, and collapse whitespace. Only return a fuzzy match when exactly one best candidate meets the threshold.

- [ ] **Step 4: Run GREEN verification**

Run: `python -m pytest tests/entities/test_normalization.py -q`

Expected: all normalization and threshold tests pass.

---

### Task 4: Transactional `EntityResolver`

**Files:**

- Create: `src/benter_peru/entities/models.py`
- Create: `src/benter_peru/entities/resolver.py`
- Create: `tests/entities/test_resolver.py`

**Interfaces:**

- `EntityResolver(engine: Engine, *, id_factory=new_ulid, clock=_utc_now)`
- `EntityResolver.resolve_sha(sha256: str) -> ResolutionReport`
- `ResolutionReport` exposes created/reused counts for race entries and all entity types plus `unconfirmed_horses`.

- [ ] **Step 1: Write resolver integration fixtures and failing tests**

Seed a migrated SQLite database with one completed version `3` extraction containing one context and multiple entry facts. Test exact normalized reuse, approved fuzzy reuse, below-threshold creation, uncertain-horse isolation, and rollback on missing/conflicting context.

- [ ] **Step 2: Add the double-resolution idempotency test**

Call `resolve_sha` twice and assert stable counts for all six tables and no duplicate `(race_id, mandil)` or `source_fact_id`.

- [ ] **Step 3: Run resolver tests and verify RED**

Run: `python -m pytest tests/entities/test_resolver.py -q`

Expected: import fails because `EntityResolver` is absent.

- [ ] **Step 4: Implement typed parsing and transaction loading**

Validate the SHA pattern, load the completed version `3` extraction by blob hash, require exactly one context fact, parse JSON fields and ISO date/decimal weight, then enter one `UnitOfWork`.

- [ ] **Step 5: Implement race and entity upserts**

Resolve exact names first. Apply thresholds `0.98` and `0.94`; disable horse fuzzy matching for reviewed observations; create those horses as `unconfirmed`. Raise typed errors for context conflicts and confirmed/unconfirmed exact-name ambiguity.

- [ ] **Step 6: Implement idempotent race-entry insertion and report counts**

Skip an entry when its `source_fact_id` already exists. Otherwise insert all foreign keys, mandil, weight, and timestamp. Return deterministic created/reused counters.

- [ ] **Step 7: Run GREEN and rollback verification**

Run: `python -m pytest tests/entities/test_resolver.py -q`

Expected: all matching, isolation, idempotency, and rollback tests pass.

---

### Task 5: CLI resolution command and end-to-end flow

**Files:**

- Modify: `src/benter_peru/cli.py`
- Modify: `tests/test_cli.py`
- Create: `tests/integration/test_entity_resolution_flow.py`

**Interfaces:**

- CLI: `benter resolve --sha <64-lowercase-hex>`
- JSON output: serialized `ResolutionReport`.
- Resolve mode constructs no HTTP client and reads only the configured SQLite database.

- [ ] **Step 1: Add failing parser and end-to-end tests**

Parse `resolve --sha`, then run synthetic local extraction and resolution twice. Assert one race, expected entities, stable second-run counts, and an unconfirmed noisy horse.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_cli.py tests/integration/test_entity_resolution_flow.py -q`

Expected: parser rejects `resolve` and no resolution JSON is emitted.

- [ ] **Step 3: Implement CLI wiring and reprocessing-safe reports**

Add the `resolve` subcommand, open/migrate the configured database, call `EntityResolver`, print JSON, and dispose the engine. Make local-run reporting use the current result/extraction rather than the immutable version's original crawl ID.

- [ ] **Step 4: Run GREEN verification**

Run: `python -m pytest tests/test_cli.py tests/integration/test_entity_resolution_flow.py -q`

Expected: CLI parse, extraction, first resolution, and second idempotent resolution pass.

---

### Task 6: Full verification and approved real data

**Files:**

- Modify only implementation/test files when verification identifies a defect.
- Never add the real PDF, SQLite database, or blob files.

**Interfaces:**

- Consumes the approved PDF path and SHA-256 from the specification.
- Produces JSON and read-only SQL evidence for the review report.

- [ ] **Step 1: Run static and complete automated verification**

Run:

```text
python -m ruff check .
python -m mypy src
python -m pytest --cov=benter_peru --cov-report=term-missing
git diff --check
```

Expected: every command exits zero and the suite has more than 50 passing tests.

- [ ] **Step 2: Reprocess the approved local PDF once with version 3**

Run `benter run --source elinformativohipico --local-file` with the verified absolute PDF path and external database/blob environment variables.

Expected: physical blob and document version remain deduplicated; one version `3` extraction stores one context and seven entry facts.

- [ ] **Step 3: Resolve twice**

Run the approved SHA with `benter resolve --sha` twice. Capture both JSON reports and compare table counts after each run.

Expected: the first creates the race/entities/entries; the second creates none and reuses the seven entries.

- [ ] **Step 4: Query review evidence**

Run read-only SQL joins for `races`, `horses`, `jockeys`, `studs`, and `race_entries`. Confirm meeting `202647`, race 1, 1000 metres, arena; seven entries; and `tNrzrAMo (usA)` as `unconfirmed`.

- [ ] **Step 5: Audit repository safety and commit**

Run:

```text
git status --short
git ls-files "*.pdf" "*.db" "*.sqlite*"
```

Expected: no protected local data is tracked. Commit implementation, migration, tests, specification, and this plan on `codex/entregable-3-entities`; do not merge.
