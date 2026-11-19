"""Run the responsible daily ingestion, materialization, and prediction flow."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from benter_peru.cli import _resolve, _resolve_picks, _run
from benter_peru.config import RuntimeConfig
from benter_peru.ml.artifacts import RealModelArtifactConfig
from benter_peru.ml.models import RealLightGBMRaceModel
from benter_peru.ui.queries import DashboardRepository
from benter_peru.ui.service import BettingStrategyService, PredictionService

JsonObject = dict[str, Any]


class DailyPipelineError(RuntimeError):
    """Raised when a discovered required artifact cannot be trusted."""


@dataclass(frozen=True, slots=True)
class DailyPipelineReport:
    status: str
    race_date: str
    collection: JsonObject
    materialized: dict[str, JsonObject]
    predictions: list[JsonObject]
    warnings: tuple[str, ...]


class DailyPipeline:
    """Coordinate existing audited components without hiding partial failures."""

    def __init__(
        self,
        *,
        collect: Callable[[], JsonObject],
        resolve_program: Callable[[str], JsonObject],
        resolve_magazine: Callable[[str], JsonObject],
        predict: Callable[[date], list[JsonObject]],
    ) -> None:
        self._collect = collect
        self._resolve_program = resolve_program
        self._resolve_magazine = resolve_magazine
        self._predict = predict

    def run(self, race_date: date) -> DailyPipelineReport:
        collection = self._collect()
        if collection.get("status") not in {"completed", "completed_with_reviews"}:
            raise DailyPipelineError("la recolección diaria no terminó correctamente")
        discovered = collection.get("discovered", [])
        documents = collection.get("documents", [])
        magazine_discovered = any(
            item.get("document_type") == "estudie_su_polla" for item in discovered
        )
        valid_documents = [
            item for item in documents if item.get("processing_status") == "extracted"
        ]
        magazines = [
            item
            for item in valid_documents
            if item.get("document_type") == "estudie_su_polla"
        ]
        if magazine_discovered and not magazines:
            raise DailyPipelineError(
                "revista descubierta, pero ausente, corrupta o sin extracción confiable"
            )

        materialized: dict[str, JsonObject] = {}
        for document in valid_documents:
            document_type = str(document.get("document_type"))
            sha256 = document.get("sha256")
            if not isinstance(sha256, str) or len(sha256) != 64:
                raise DailyPipelineError("documento procesado sin SHA-256 válido")
            if document_type == "programa_monterrico":
                materialized[document_type] = self._resolve_program(sha256)
            elif document_type == "estudie_su_polla":
                materialized[document_type] = self._resolve_magazine(sha256)

        warnings = (
            ()
            if magazine_discovered
            else ("Estudie su Polla no fue encontrada",)
        )
        return DailyPipelineReport(
            status="completed" if not warnings else "completed_with_warnings",
            race_date=race_date.isoformat(),
            collection=collection,
            materialized=materialized,
            predictions=self._predict(race_date),
            warnings=warnings,
        )


def _predict_date(config: RuntimeConfig, target_date: date) -> list[JsonObject]:
    artifact_config = RealModelArtifactConfig.from_env()
    predictor = RealLightGBMRaceModel.load(
        model_path=artifact_config.model_path,
        dataset_path=artifact_config.dataset_path,
        expected_sha256=artifact_config.expected_sha256,
    )
    prediction_service = PredictionService(predictor)
    betting_service = BettingStrategyService()
    repository = DashboardRepository.open(config.database_path)
    try:
        reports: list[JsonObject] = []
        for race in repository.races_on_date(target_date):
            participants = repository.participants_for_race(race.id)
            if len(participants) < 2:
                continue
            prediction = prediction_service.for_race(race, participants)
            strategy = betting_service.analyze(prediction, {})
            reports.append(
                {
                    "meeting_code": race.meeting_code,
                    "race_number": race.race_number,
                    "distance_meters": race.distance_meters,
                    "surface": race.surface,
                    "prediction": asdict(prediction),
                    "exactas": [asdict(item) for item in strategy.exactas],
                    "trifectas": [asdict(item) for item in strategy.trifectas],
                    "market_recommendation": None,
                }
            )
        return reports
    finally:
        repository.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    config = RuntimeConfig.from_env()
    pipeline = DailyPipeline(
        collect=lambda: _run(config),
        resolve_program=lambda sha256: _resolve(config, sha256),
        resolve_magazine=lambda sha256: _resolve_picks(config, sha256),
        predict=lambda target: _predict_date(config, target),
    )
    report = pipeline.run(arguments.date)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
