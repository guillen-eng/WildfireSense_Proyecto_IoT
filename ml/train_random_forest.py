"""Train exploratory Random Forest ONLY with externally labeled independent episodes.

Run from repository root: python -m ml.train_random_forest ...
No labels or splits are generated here. No model is loaded by the live Edge yet.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
from edge.features import FEATURE_NAMES


def train_dataset(path, model_out, report_out, seed=42):
    data = pd.read_csv(path)
    expected = set(FEATURE_NAMES) | {"label", "group_id", "split"}
    missing = sorted(expected - set(data.columns))
    if missing:
        raise ValueError(f"Dataset missing columns: {missing}")
    if data.empty or data[["label", "group_id", "split"]].isna().any().any():
        raise ValueError("Missing labels/group IDs/splits")
    if not data["label"].isin([0, 1]).all():
        raise ValueError("Binary labels must be 0/1")
    if not data["split"].isin(["train", "test"]).all():
        raise ValueError("split must be explicitly train/test (by independent episodes)")
    groups_train = set(data.loc[data.split == "train", "group_id"].astype(str))
    groups_test = set(data.loc[data.split == "test", "group_id"].astype(str))
    if not groups_train or not groups_test or groups_train & groups_test:
        raise ValueError("Train and test groups must be disjoint and nonempty")
    numeric = data[list(FEATURE_NAMES)].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("NaN/infinite features are not allowed")
    train_mask = data.split == "train"
    test_mask = data.split == "test"
    train_y = data.loc[train_mask, "label"]
    test_y = data.loc[test_mask, "label"]
    if set(train_y) != {0, 1} or set(test_y) != {0, 1}:
        raise ValueError("Train/test must each include both classes")
    model = RandomForestClassifier(
        n_estimators=200, min_samples_leaf=2, class_weight="balanced_subsample",
        random_state=seed, n_jobs=1,
    )
    model.fit(numeric.loc[train_mask], train_y)
    predictions = model.predict(numeric.loc[test_mask])
    metrics = {
        "experimental_only": True,
        "dataset": Path(path).name,
        "train_rows": int(train_mask.sum()), "test_rows": int(test_mask.sum()),
        "train_groups": len(groups_train), "test_groups": len(groups_test),
        "precision": float(precision_score(test_y, predictions, zero_division=0)),
        "recall": float(recall_score(test_y, predictions, zero_division=0)),
        "f1": float(f1_score(test_y, predictions, zero_division=0)),
        "confusion_matrix_0_1": confusion_matrix(test_y, predictions, labels=[0, 1]).tolist(),
        "warning": "Metrics on labeled synthetic episodes do not validate real wildfire detection",
    }
    artifact = {
        "model": model, "schema_version": 1, "feature_names": list(FEATURE_NAMES),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "label_definition": "synthetic_fire_window_binary", "seed": seed,
    }
    Path(model_out).parent.mkdir(parents=True, exist_ok=True)
    Path(report_out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_out)
    Path(report_out).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Train exploratory Random Forest on labeled features")
    parser.add_argument("--dataset", required=True, help="CSV: 18 feature columns, label, group_id, split")
    parser.add_argument("--model-out", default="edge/models/random_forest_v1.joblib")
    parser.add_argument("--report-out", default="ml/results/rf_metrics.json")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train_dataset(args.dataset, args.model_out, args.report_out, args.seed), indent=2))


if __name__ == "__main__":
    main()
