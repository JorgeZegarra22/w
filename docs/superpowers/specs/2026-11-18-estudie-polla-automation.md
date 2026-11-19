# Estudie su Polla and Daily Automation Design

**Status:** Implemented and verified
**Date:** 2026-11-19
**Target branch:** `codex/entregable-10-estudie-polla-automation`

## Objective

Extract ordered journalist selections from text-layer editions of “Estudie su
Polla”, preserve page-level evidence, materialize auditable picks, display them
beside mathematical probabilities, and provide a local daily pipeline. A missing
magazine is non-fatal; a discovered but corrupt or structurally ambiguous
magazine never produces an official pick silently.

## Extraction Contract

`EstudiePollaExtractor.extract(source)` accepts a PDF path or binary stream. It
requires a text layer and recognizes explicit meeting, race, journalist, and
selection markers. The deterministic fixture format is:

```text
REUNION 202647
PRONOSTICO DE LA REVISTA
CARRERA | PERIODISTA | SELECCION
1 | ESTUDIE SU POLLA | 3 MR. PEGGY, 1 SHOTRA, 5 VIEJO LINDO
```

Each ordered selection emits one `journalist_pick` fact containing meeting,
race, rank, mandil, raw horse name, and journalist. Evidence covers the source
row. Missing mandil or malformed selection produces a low-confidence review
fact with the raw text and no inferred identity. A PDF without text returns
`requires_ocr=True`. A text PDF containing explicit magazine markers but no
parseable rows raises `EstudiePollaExtractionError`.

`ExtractionRouter` selects this extractor only for document type
`estudie_su_polla`; program PDFs retain the existing table extractor. Extractor
identity advances to version 5.0 and includes document type in the processing
fingerprint.

## Persistence

Migration `20261118_0004` creates `journalist_picks` with source document and
fact foreign keys, meeting code, race number, rank, optional mandil, raw horse
name, journalist, confidence, review flag, and timestamp. Unique source fact and
`(source_document_version_id, meeting_code, race_number, selection_rank)`
constraints provide idempotency. Checks enforce positive race/rank/mandil and a
confidence range of zero through one.

`JournalistPickResolver.resolve_sha()` loads the latest completed v5 extraction,
validates every JSON payload, and inserts or reuses picks within one UnitOfWork.
Review facts are persisted as review picks but are never fuzzily reassigned.

## Dashboard

The read-only repository returns picks by meeting and race. Reconciliation uses
mandil first, then a unique normalized horse name. Confirmed picks display
`★ <rank>`; review picks display `⚠ <raw text>`; absent picks display `-`.
Predictions and strategy views use the same projection and never write state.

## Daily Pipeline

`scripts/daily_pipeline.py` executes the existing responsible network run with
both document types enabled, resolves every downloaded program and magazine,
then calculates real-model predictions and theoretical ordered combinations for
the requested date. It emits JSON only.

- No discovered magazine: warning and successful continuation.
- Discovered and processed magazine: materialize picks.
- Discovered magazine without a valid processed PDF or with extraction failure:
  fail the run explicitly.

The job remains local because SQLite, model, and dataset are ignored artifacts.
`docs/operations/daily-pipeline.md` documents Windows Task Scheduler and cron;
no misleading GitHub Actions workflow is created.

## Testing

Tests cover clear, absent, ambiguous, corrupt, and image-only magazine inputs;
migration constraints and resolver idempotency; dashboard labels; routing; and
daily pipeline fail-soft/fail-closed behavior. Existing tests remain green.

## Non-Goals

- OCR.
- Guessing missing mandils or horse identities.
- Remote CI scheduling with unavailable local artifacts.
- Automated wagering or persistence of market prices.
