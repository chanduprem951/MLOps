import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ml import workflow


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    from app import main
    root = tmp_path_factory.mktemp("model")
    workflow.ROOT = root
    for step in ["data", "preprocess", "features", "train", "evaluate", "validate", "gate"]:
        workflow.run(step)
    main.ROOT = root
    with TestClient(main.app) as client:
        yield client


def test_prediction_and_version(trained):
    response = trained.post("/predict", json=dict(zip(workflow.FEATURES, [5.1, 3.5, 1.4, .2])))
    assert response.status_code == 200
    assert response.json()["label"] == "setosa"
    assert sum(response.json()["probabilities"]) == pytest.approx(1)
    assert trained.get("/ready").json()["version"] == response.json()["model_version"]


def test_bad_payload(trained):
    assert trained.post("/predict", json=dict(zip(workflow.FEATURES, [-1, 3, 1, .2]))).status_code == 422
    assert trained.post("/predict", json={}).status_code == 422


def test_bad_data():
    with pytest.raises(ValueError):
        workflow.validate(pd.DataFrame({"wrong": [1]}))


def test_monitoring(trained):
    assert trained.get("/health").status_code == 200
    assert "api_requests_total" in trained.get("/metrics").text


def test_mismatched_model_rejected(tmp_path, monkeypatch):
    import json
    from app import main
    (tmp_path / "model.joblib").write_bytes(b"tampered model")
    (tmp_path / "manifest.json").write_text(json.dumps({"model_sha256": "0" * 64}))
    monkeypatch.setattr(main, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="release manifest"):
        with TestClient(main.app):
            pass
