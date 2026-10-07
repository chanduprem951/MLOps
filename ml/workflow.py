"""Reproducible training with held-out quality gates and versioned provenance."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
FEATURES = ["sepal_length", "sepal_width", "petal_length", "petal_width"]


def validate(frame):
    if list(frame.columns) != FEATURES + ["target"]:
        raise ValueError("Expected four ordered feature columns and target")
    if len(frame) < 90 or frame.isna().any().any():
        raise ValueError("Insufficient rows or missing data")
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Data must be finite")
    if not frame[FEATURES].gt(0).all().all() or not frame[FEATURES].le(20).all().all():
        raise ValueError("Features must be in (0, 20]")
    if set(frame.target.unique()) != {0, 1, 2} or frame.target.value_counts().min() < 20:
        raise ValueError("All three classes require at least 20 rows")


def run(step):
    ROOT.mkdir(exist_ok=True, parents=True)
    if step == "data":
        source = Path(os.getenv("TRAINING_DATA", "data/current.csv"))
        if source.exists():
            frame = pd.read_csv(source)
        else:
            if os.getenv("REQUIRE_TRAINING_DATA") == "true":
                raise ValueError("Retraining requires TRAINING_DATA from an approved versioned source")
            iris = load_iris()
            frame = pd.DataFrame(iris.data, columns=FEATURES)
            frame["target"] = iris.target
        validate(frame)
        frame.to_csv(ROOT / "data.csv", index=False)
    elif step == "preprocess":
        frame = pd.read_csv(ROOT / "data.csv")
        validate(frame)
        train, test = train_test_split(frame, test_size=.25, stratify=frame.target, random_state=42)
        train.to_csv(ROOT / "train.csv", index=False)
        test.to_csv(ROOT / "test.csv", index=False)
    elif step == "features":
        # Scaling is fitted only inside the training pipeline; no leakage from test rows.
        (ROOT / "features.json").write_text(json.dumps({"columns": FEATURES, "transform": "StandardScaler"}))
    elif step == "train":
        train = pd.read_csv(ROOT / "train.csv")
        model = Pipeline([("scale", StandardScaler()), ("classifier", LogisticRegression(max_iter=500))])
        model.fit(train[FEATURES], train.target)
        joblib.dump(model, ROOT / "model.joblib")
    elif step == "evaluate":
        test = pd.read_csv(ROOT / "test.csv")
        model = joblib.load(ROOT / "model.joblib")
        prediction = model.predict(test[FEATURES])
        metrics = {"accuracy": accuracy_score(test.target, prediction),
                   "macro_f1": f1_score(test.target, prediction, average="macro"), "test_rows": len(test)}
        (ROOT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    elif step == "validate":
        model = joblib.load(ROOT / "model.joblib")
        assert model.n_features_in_ == 4
        assert list(model.classes_) == [0, 1, 2]
        probabilities = model.predict_proba(pd.DataFrame([[5.1, 3.5, 1.4, .2]], columns=FEATURES))
        assert np.isfinite(probabilities).all() and np.allclose(probabilities.sum(axis=1), 1)
    elif step == "gate":
        metrics = json.loads((ROOT / "metrics.json").read_text())
        if metrics["accuracy"] < .90 or metrics["macro_f1"] < .90:
            raise ValueError(f"Model quality gate failed: {metrics}")
        manifest = {"version": os.getenv("BUILD_BUILDID", "local"),
                    "commit": os.getenv("BUILD_SOURCEVERSION", "local"), "metrics": metrics,
                    "data_sha256": hashlib.sha256((ROOT / "data.csv").read_bytes()).hexdigest(),
                    "model_sha256": hashlib.sha256((ROOT / "model.joblib").read_bytes()).hexdigest()}
        (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2))
        baseline = pd.read_csv(ROOT / "train.csv")[FEATURES]
        baseline.to_csv(ROOT / "baseline.csv", index=False)
    else:
        raise ValueError(step)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["data", "preprocess", "features", "train", "evaluate", "validate", "gate", "all"])
    step = parser.parse_args().step
    for task in (["data", "preprocess", "features", "train", "evaluate", "validate", "gate"] if step == "all" else [step]):
        run(task)
