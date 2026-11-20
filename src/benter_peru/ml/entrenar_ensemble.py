"""Train and evaluate a fixed ensemble on the original outer date split."""

from __future__ import annotations

import argparse
import json
import pickle
from hashlib import sha256
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-untyped]
from sklearn.metrics import log_loss, roc_auc_score  # type: ignore[import-untyped]
from xgboost import XGBClassifier

from benter_peru.ml.clean_training import clean_features, temporal_split
from benter_peru.ml.ensemble import (
    MODEL_WEIGHTS,
    blend_winner_scores,
    category_levels,
    encode,
    winner_scores,
)
from benter_peru.ml.real_features import LIGHTGBM_FEATURE_COLUMNS


def train_ensemble(dataset_path: Path, output_path: Path) -> dict[str, object]:
    content = dataset_path.read_bytes()
    frame = clean_features(pd.read_csv(BytesIO(content)))
    train, validation, cutoff = temporal_split(frame)
    levels = category_levels(train)
    x_train, x_validation = encode(train, levels), encode(validation, levels)
    y_train, y_validation = train["Target_Ganador"], validation["Target_Ganador"]
    weights = dict(MODEL_WEIGHTS)
    models = {
        "lightgbm": LGBMClassifier(
            objective="binary",
            learning_rate=0.03,
            n_estimators=500,
            num_leaves=31,
            max_depth=6,
            min_child_samples=25,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=3,
            verbosity=-1,
        ),
        "xgboost": XGBClassifier(
            objective="binary:logistic",
            learning_rate=0.03,
            n_estimators=400,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=3,
            tree_method="hist",
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=16,
            min_samples_leaf=10,
            random_state=42,
            n_jobs=3,
        ),
    }
    scores = {}
    for name, model in models.items():
        model.fit(x_train, y_train)
        scores[name] = winner_scores(model, x_validation)
    scores["ensemble"] = blend_winner_scores(scores, weights)
    report: dict[str, object] = {
        "cutoff": cutoff.date().isoformat(),
        "train_rows": len(train),
        "validation_rows": len(validation),
        "weights": weights,
        "training_start": train["Fecha_Dt"].min().date().isoformat(),
        "training_end": train["Fecha_Dt"].max().date().isoformat(),
        "metrics": {
            name: {
                "auc_roc": float(roc_auc_score(y_validation, values)),
                "log_loss": float(log_loss(y_validation, values)),
            }
            for name, values in scores.items()
        },
    }
    artifact = {
        **report,
        "contract": "ensemble-v1",
        "models": models,
        "feature_columns": LIGHTGBM_FEATURE_COLUMNS,
        "levels": levels,
        "dataset_sha256": sha256(content).hexdigest(),
        "versions": {name: version(name) for name in ("lightgbm", "xgboost", "scikit-learn")},
    }
    payload = pickle.dumps(artifact, protocol=pickle.HIGHEST_PROTOCOL)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as stream:
        stream.write(payload)
    return {**report, "artifact_sha256": sha256(payload).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(train_ensemble(args.dataset, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
