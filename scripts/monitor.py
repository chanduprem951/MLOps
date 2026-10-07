"""Offline drift on approved samples, and optional supervised model-performance drift."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

from ml.workflow import FEATURES


def monitor(baseline_path, current_path, output, model_path=None):
    baseline = pd.read_csv(baseline_path)
    current = pd.read_csv(current_path)
    if len(current) < 100:
        raise ValueError("At least 100 observations required")
    if len(baseline) < 100:
        raise ValueError("At least 100 baseline observations required")
    for frame in [baseline, current]:
        if not set(FEATURES).issubset(frame.columns) or not np.isfinite(frame[FEATURES]).all().all():
            raise ValueError("Invalid monitoring samples")
        if not frame[FEATURES].gt(0).all().all() or not frame[FEATURES].le(20).all().all():
            raise ValueError("Monitoring features must be in (0, 20]")
    scores = {}
    for feature in FEATURES:
        edges = np.unique(np.quantile(baseline[feature], np.linspace(0, 1, 11)))
        if len(edges) == 1:
            value = edges[0]
            edges = np.array([-np.inf, value - 1e-6, value + 1e-6, np.inf])
        else:
            edges[0], edges[-1] = -np.inf, np.inf
        expected = np.histogram(baseline[feature], edges)[0] / len(baseline)
        actual = np.histogram(current[feature], edges)[0] / len(current)
        expected, actual = np.clip(expected, .0001, 1), np.clip(actual, .0001, 1)
        scores[feature] = float(np.sum((actual - expected) * np.log(actual / expected)))
    accuracy = None
    if model_path and "target" in current:
        if not current.target.isin([0, 1, 2]).all():
            raise ValueError("Invalid ground truth labels")
        accuracy = float(accuracy_score(current.target, joblib.load(model_path).predict(current[FEATURES])))
    report = {"psi": scores, "accuracy": accuracy,
              "retrain": max(scores.values()) > .2 or (accuracy is not None and accuracy < .90)}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("current")
    parser.add_argument("--output", default="artifacts/drift.json")
    parser.add_argument("--model")
    args = parser.parse_args()
    report = monitor(args.baseline, args.current, args.output, args.model)
    print(json.dumps(report))
    print("##vso[task.setvariable variable=retrain;isOutput=true]" + str(report["retrain"]).lower())
