import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from ml.workflow import FEATURES

ROOT = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
REQUESTS = Counter("api_requests_total", "Requests", ["route", "status"])
LATENCY = Histogram("api_latency_seconds", "Latency", ["route"])
PREDICTIONS = Counter("model_predictions_total", "Predictions", ["class_id", "version"])
logger = logging.getLogger("mlops")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    # Load only trusted artifacts produced by this project's CI; joblib is executable serialization.
    app.state.manifest = json.loads((ROOT / "manifest.json").read_text())
    model_path = ROOT / "model.joblib"
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != app.state.manifest["model_sha256"]:
        raise ValueError("Model does not match the release manifest")
    app.state.model = joblib.load(model_path)
    yield


app = FastAPI(title="Azure MLOps Iris API", lifespan=lifespan)


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sepal_length: float = Field(gt=0, le=20, allow_inf_nan=False)
    sepal_width: float = Field(gt=0, le=20, allow_inf_nan=False)
    petal_length: float = Field(gt=0, le=20, allow_inf_nan=False)
    petal_width: float = Field(gt=0, le=20, allow_inf_nan=False)


@app.middleware("http")
async def telemetry(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    # Bound label cardinality; never record payloads or query strings.
    route = request.scope.get("route")
    path = route.path if route else "unknown"
    REQUESTS.labels(path, response.status_code).inc()
    LATENCY.labels(path).observe(time.perf_counter() - start)
    logger.info(json.dumps({"route": path, "status": response.status_code,
                            "duration_ms": round((time.perf_counter() - start) * 1000, 2)}))
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not hasattr(app.state, "model"):
        raise HTTPException(503, "Model unavailable")
    return {"status": "ready", "version": app.state.manifest["version"]}


@app.get("/model")
def metadata():
    return app.state.manifest


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict")
def predict(payload: PredictionRequest):
    probabilities = app.state.model.predict_proba(pd.DataFrame([payload.model_dump()], columns=FEATURES))[0]
    class_id = int(probabilities.argmax())
    version = app.state.manifest["version"]
    PREDICTIONS.labels(str(class_id), version).inc()
    return {"class_id": class_id, "label": ["setosa", "versicolor", "virginica"][class_id],
            "probabilities": probabilities.tolist(), "model_version": version}
