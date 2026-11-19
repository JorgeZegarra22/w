from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from scripts.daily_pipeline import DailyPipeline, DailyPipelineError


def _document(document_type: str, status: str = "extracted") -> dict[str, Any]:
    return {
        "document_type": document_type,
        "sha256": document_type.ljust(64, "0")[:64],
        "processing_status": status,
    }


def _pipeline(
    collection: dict[str, Any], calls: list[tuple[str, str]]
) -> DailyPipeline:
    def resolver(kind: str) -> Callable[[str], dict[str, Any]]:
        def resolve(sha256: str) -> dict[str, Any]:
            calls.append((kind, sha256))
            return {"created": 1}

        return resolve

    return DailyPipeline(
        collect=lambda: collection,
        resolve_program=resolver("program"),
        resolve_magazine=resolver("magazine"),
        predict=lambda target: [{"date": target.isoformat(), "race_number": 1}],
    )


def test_missing_magazine_is_a_warning_and_program_continues() -> None:
    calls: list[tuple[str, str]] = []
    collection = {
        "status": "completed_with_reviews",
        "discovered": [{"document_type": "programa_monterrico"}],
        "documents": [_document("programa_monterrico")],
    }

    report = _pipeline(collection, calls).run(date(2026, 11, 22))

    assert report.status == "completed_with_warnings"
    assert report.warnings == ("Estudie su Polla no fue encontrada",)
    assert [kind for kind, _ in calls] == ["program"]
    assert report.predictions[0]["race_number"] == 1


def test_present_magazine_is_materialized_before_predictions() -> None:
    calls: list[tuple[str, str]] = []
    collection = {
        "status": "completed",
        "discovered": [
            {"document_type": "programa_monterrico"},
            {"document_type": "estudie_su_polla"},
        ],
        "documents": [
            _document("programa_monterrico"),
            _document("estudie_su_polla"),
        ],
    }

    report = _pipeline(collection, calls).run(date(2026, 11, 22))

    assert report.status == "completed"
    assert report.warnings == ()
    assert [kind for kind, _ in calls] == ["program", "magazine"]
    assert report.materialized["estudie_su_polla"]["created"] == 1


@pytest.mark.parametrize("status", ["failed", "needs_ocr"])
def test_discovered_invalid_magazine_fails_closed(status: str) -> None:
    calls: list[tuple[str, str]] = []
    collection = {
        "status": "completed",
        "discovered": [{"document_type": "estudie_su_polla"}],
        "documents": [_document("estudie_su_polla", status)],
    }

    with pytest.raises(DailyPipelineError, match="revista descubierta"):
        _pipeline(collection, calls).run(date(2026, 11, 22))

    assert calls == []
