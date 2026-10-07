import pandas as pd
import pytest

from ml.workflow import FEATURES
from scripts.monitor import monitor


def test_drift_triggers_only_shift(tmp_path):
    base = pd.DataFrame({feature: [1 + i / 100 for i in range(150)] for feature in FEATURES})
    base.to_csv(tmp_path / "base.csv", index=False)
    base.to_csv(tmp_path / "current.csv", index=False)
    assert not monitor(tmp_path / "base.csv", tmp_path / "current.csv", tmp_path / "report.json")["retrain"]
    (base + 5).to_csv(tmp_path / "current.csv", index=False)
    assert monitor(tmp_path / "base.csv", tmp_path / "current.csv", tmp_path / "report.json")["retrain"]


def test_small_monitoring_batch_rejected(tmp_path):
    frame = pd.DataFrame({feature: [1] * 5 for feature in FEATURES})
    frame.to_csv(tmp_path / "small.csv", index=False)
    with pytest.raises(ValueError):
        monitor(tmp_path / "small.csv", tmp_path / "small.csv", tmp_path / "report.json")


def test_constant_baseline_detects_shift(tmp_path):
    base = pd.DataFrame({feature: [1.0] * 150 for feature in FEATURES})
    base.to_csv(tmp_path / "base.csv", index=False)
    base.to_csv(tmp_path / "current.csv", index=False)
    assert not monitor(tmp_path / "base.csv", tmp_path / "current.csv", tmp_path / "report.json")["retrain"]
    (base + 1).to_csv(tmp_path / "current.csv", index=False)
    assert monitor(tmp_path / "base.csv", tmp_path / "current.csv", tmp_path / "report.json")["retrain"]
