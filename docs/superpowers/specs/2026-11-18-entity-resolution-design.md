# Entregable 3: Entity Resolution and Horse Record Design

**Status:** Approved and implemented

**Date:** 2026-11-18

**Scope:** Extend extraction with race context and stud data, introduce portable master
entity tables, resolve the latest structured facts for a document hash, and create
idempotent race entries without allowing uncertain horse names to contaminate confirmed
identities.

> **Implementation note (2026-11-18):** the first real-data version `3` run exposed
> non-linear word ordering in the printed date. That run remains immutable for
> traceability; the corrected geometric date recovery is version `3.1`. References to
> version `3` below describe this v3 extractor family, whose resolution target is `3.1`.

## 1. Goals

- Reprocess an existing document hash when the extractor version changes.
- Extract the stud for every first-race participant.
- Extract meeting code, race number, scheduled date, distance, and surface as a
  `race_context` fact.
- Resolve horses, jockeys, trainers, and studs conservatively.
- Create the race and its entries transactionally.
- Preserve uncertain horse names as separate `unconfirmed` entities.
- Make `benter resolve --sha <sha256>` safe to repeat without duplicates.

## 2. Non-goals

- No human-review interface in this phase.
- No automatic correction of OCR-corrupted horse names.
- No merging or deleting existing master entities.
- No resolution across external registries.
- No predictive model or historical-performance calculation.
- Only the first race is resolved in this increment.

## 3. Extraction Version 3

The current persisted extraction contract is version `2`. The new extractor identity is:

- Name: `pdfplumber-hipico-text`
- Version: `3`
- Input fingerprint: SHA-256 of `<blob_sha256>:pdfplumber-hipico-text:3`

The fingerprint remains unique in `extraction_runs` and `processing_tasks`. Therefore, a
blob processed by version `2` receives one new version `3` extraction run, while a second
version `3` execution is deduplicated.

The extractor name and version must be defined once in the extraction package and consumed
by the orchestrator. They must not be duplicated as unrelated string literals.

### 3.1 Stud column

On the approved source layout, the stud is between weight and jockey. The proportional
bands are:

| Field | Page-width band |
|---|---:|
| Mandil | `< 0.09` |
| Horse | `0.09 - 0.285` |
| Weight | `0.285 - 0.38` |
| Stud | `0.435 - 0.56` |
| Jockey | `0.56 - 0.67` |
| Trainer | `0.67 - 0.80` |

The mandil continues to anchor each logical row. Words are assigned to vertical windows
bounded by the midpoint between consecutive mandil anchors. The evidence bounding box
encloses the whole row from mandil through trainer.

Each `race_entry` normalized value uses this shape:

```json
{
  "mandil": 1,
  "horse_name": "WAYTT",
  "weight": "56.00",
  "stud": "S.B.P.",
  "jockey": "J H SUAREZ",
  "trainer": "R Melgarejo",
  "horse_requires_review": false
}
```

Mixed-case or replacement-character noise in the horse band is preserved exactly. It sets
`horse_requires_review=true`, lowers fact confidence to `0.55`, and sets the fact's
`requires_review=true`. Clean rows use confidence `0.95`.

### 3.2 Race context

Version `3` creates one `race_context` fact for the first race. It reads:

- Meeting code from a tolerant match beginning with `REUN` and ending in six digits.
- Scheduled date from the program header's day, Spanish month, and year.
- Race number from `1ra. CAR.`.
- Distance from the first race header's `DISTANCIA ... METROS` segment.
- Surface from the first race header (`ARENA` or `CESPED`).

The real source's `REUN|ON202647` is accepted without rewriting its evidence. The normalized
value is:

```json
{
  "meeting_code": "202647",
  "race_number": 1,
  "scheduled_date": "2026-11-21",
  "distance_meters": 1000,
  "surface": "arena"
}
```

The subject key is `meeting:202647:race:1`. Evidence remains on page 1 and its bounding box
encloses the meeting/date header and first-race header used to derive the fields. If any
required context field is absent, no partial `race_context` fact is emitted; extraction logs
a warning and entity resolution refuses to create a race.

## 4. Portable Database Migration

Alembic revision `20261118_0002` revises `20261118_0001`. It adds exactly six tables using
portable SQLAlchemy types and named constraints.

### 4.1 Master entity tables

`horses`, `jockeys`, `trainers`, and `studs` share:

| Column | Type | Rules |
|---|---|---|
| `id` | `String(26)` | Primary key, application-generated ULID |
| `canonical_name` | `String(255)` | Not null |
| `normalized_name` | `String(255)` | Not null, unique |
| `confirmation_status` | `String(20)` | `confirmed` or `unconfirmed` |
| `created_at` | timezone-aware `DateTime` | Not null |

Each table has a named unique constraint on `normalized_name`, an ID-length check, a
non-empty-name check, and a confirmation-status check.

### 4.2 `races`

| Column | Type | Rules |
|---|---|---|
| `id` | `String(26)` | Primary key |
| `source_document_version_id` | `String(26)` | FK to `document_versions.id`, not null |
| `meeting_code` | `String(20)` | Not null |
| `race_number` | `Integer` | Positive |
| `scheduled_date` | `Date` | Not null |
| `distance_meters` | `Integer` | Positive |
| `surface` | `String(30)` | `arena` or `cesped` |
| `confirmation_status` | `String(20)` | `confirmed` or `unconfirmed` |
| `created_at` | timezone-aware `DateTime` | Not null |

`(meeting_code, race_number)` is unique. If a later resolution observes an existing race
with conflicting date, distance, surface, or source document version, it raises a typed
context-conflict error and rolls back instead of silently overwriting the race.

### 4.3 `race_entries`

| Column | Type | Rules |
|---|---|---|
| `id` | `String(26)` | Primary key |
| `race_id` | `String(26)` | FK to `races.id`, not null |
| `horse_id` | `String(26)` | FK to `horses.id`, not null |
| `jockey_id` | `String(26)` | FK to `jockeys.id`, not null |
| `trainer_id` | `String(26)` | FK to `trainers.id`, not null |
| `stud_id` | `String(26)` | FK to `studs.id`, not null |
| `source_fact_id` | `String(26)` | FK to `extracted_facts.id`, not null, unique |
| `mandil` | `Integer` | Positive |
| `weight` | `Numeric(5,2)` | Positive |
| `created_at` | timezone-aware `DateTime` | Not null |

`(race_id, mandil)` is unique. The unique `source_fact_id` makes repeated resolution of the
same version `3` extraction idempotent.

The schema metadata, Alembic upgrade/downgrade, table inventory tests, unique-constraint
tests, foreign-key tests, and recovery indexes are updated together. The migration must run
on SQLite and remain portable to PostgreSQL.

## 5. Name Normalization and Matching

`normalize_name(value: str) -> str` performs Unicode NFKD decomposition, removes combining
marks, replaces punctuation with spaces, case-folds, and collapses whitespace. It does not
change the stored `canonical_name`.

Example:

```text
J H SUAREZ   -> j h suarez
J. H. Suarez -> j h suarez
```

Resolution order for every entity is:

1. Look for an exact `normalized_name` match.
2. If allowed for that observation, compare against existing candidates with
   `difflib.SequenceMatcher`.
3. Reuse the single best candidate only when its score meets the entity threshold.
4. Otherwise create a new entity using the observed value as `canonical_name`.

Thresholds:

| Entity | Fuzzy threshold |
|---|---:|
| Horse, confirmed observation | `0.98` |
| Jockey | `0.94` |
| Trainer | `0.94` |
| Stud | `0.94` |

Ties at the best score are treated as ambiguous and create a new entity rather than picking
arbitrarily.

### 5.1 Uncertain horse policy

When `horse_requires_review=true` or the source fact requires review:

- Exact normalized lookup may reuse the same existing `unconfirmed` horse.
- An exact match that exists only as `confirmed` raises a typed ambiguity error; it is not
  reused and no duplicate violating `normalized_name` uniqueness is attempted.
- Fuzzy matching is disabled.
- A missing exact match creates an `unconfirmed` horse.
- It is linked to the race entry so all seven source rows remain represented.
- It is never merged into a confirmed horse automatically.

Consequently `tNrzrAMo (usA)` is stored separately as `unconfirmed` and is not matched to
`INIZIAMO`.

Jockey, trainer, and stud resolution remains independent of horse-field noise. A noisy horse
does not force otherwise clean participant fields into `unconfirmed` status.

## 6. Resolver Transaction

`src/benter_peru/entities/resolver.py` exposes an `EntityResolver` with a method equivalent
to:

```python
resolve_sha(sha256: str) -> ResolutionReport
```

The resolver:

1. Validates the lowercase 64-character SHA-256.
2. Selects the completed version `3` extraction for the matching document blob. Version `3`
   idempotency guarantees at most one such extraction fingerprint per blob.
3. Loads exactly one `race_context` and all `race_entry` facts from that extraction.
4. Validates the normalized JSON contract before writing master data.
5. Starts one `UnitOfWork` transaction.
6. Creates or validates the race.
7. Resolves and upserts each horse, jockey, trainer, and stud.
8. Inserts missing race entries and skips entries already linked by `source_fact_id`.
9. Commits all entities and entries together; any error rolls everything back.

The report returns created and reused counts for races, entries, and every entity type. It
also reports how many horses remain unconfirmed.

## 7. CLI Contract

The command is:

```text
benter resolve --sha <64-lowercase-hex>
```

It reads only database configuration; it never constructs an HTTP client. Output is JSON and
contains the resolution counts and unconfirmed-horse count.

The local-run report is adjusted for reprocessing an existing document version: it reports
facts from the extraction created or deduplicated for the current blob rather than assuming
the immutable document version belongs to the newest crawl run.

## 8. Real-data Execution

The approved real document is reprocessed from its existing local path with extractor
version `3`. The blob remains physically deduplicated by SHA-256. The expected sequence is:

```text
benter run --source elinformativohipico --local-file <approved-local-pdf>
benter resolve --sha cc1d6e938a1b8532d446cf9eaf8a46682f7526320bc86fc5bb83f6362fd97abc
benter resolve --sha cc1d6e938a1b8532d446cf9eaf8a46682f7526320bc86fc5bb83f6362fd97abc
```

The second resolution must leave entity, race, and race-entry counts unchanged.

## 9. Testing Strategy

All behavior is developed test-first.

- Migration tests verify 26 application tables, named unique constraints, checks, foreign
  keys, and upgrade/downgrade behavior.
- Synthetic PDF tests verify stud geometry, `race_context`, evidence page/bbox, noisy horse
  preservation, and extractor version `3` output.
- Normalization tests prove `J H SUAREZ` and `J. H. Suarez` normalize identically.
- Resolver tests cover exact reuse, fuzzy reuse at the approved thresholds, below-threshold
  creation, tie ambiguity, and no fuzzy matching for uncertain horses.
- Integration tests run extraction and resolution on temporary SQLite, then resolve twice and
  assert stable counts.
- Rollback tests inject malformed or conflicting context and verify that no partial entities
  or race entries remain.
- Ruff, Mypy, and the complete Pytest suite must pass before real-data execution.

## 10. Acceptance Criteria

- Extractor version `3` creates one context fact and seven entry facts for the approved first
  race, including stud values.
- Reprocessing the same blob creates one new version `3` extraction without duplicating the
  blob or document version.
- Resolution creates one race for meeting `202647`, race 1, 1000 metres, arena.
- Resolution creates seven race entries and their linked master entities.
- `tNrzrAMo (usA)` is present as an `unconfirmed` horse and is not merged with another horse.
- A second `resolve` command creates no additional race, entity, or entry rows.
- The real PDF, blob, and SQLite database remain outside Git.
- The implementation is committed only to `codex/entregable-3-entities` and awaits human
  approval before merge.
