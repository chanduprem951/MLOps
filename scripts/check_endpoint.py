"""Live contract, negative-input and latency checks; fails on any failed gate."""
import argparse
import concurrent.futures
import statistics
import time

import httpx

PAYLOAD = {"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": .2}


def check(url, mode, version=None):
    headers = {}
    import os
    if os.getenv("API_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["API_TOKEN"]
    with httpx.Client(base_url=url, timeout=15, headers=headers) as client:
        for path in ["/health", "/ready", "/model"]:
            response = client.get(path)
            response.raise_for_status()
        if version:
            assert str(client.get("/ready").json()["version"]) == str(version), "Wrong deployed model"
        def prediction(_):
            start = time.perf_counter()
            response = client.post("/predict", json=PAYLOAD)
            response.raise_for_status()
            assert response.json()["label"] == "setosa"
            return time.perf_counter() - start
        prediction(0)
        if mode in {"api", "security", "integration"}:
            assert client.post("/predict", json={}).status_code == 422
            assert client.post("/predict", json={**PAYLOAD, "petal_width": -1}).status_code == 422
            assert client.post("/predict", json={**PAYLOAD, "unexpected": "value"}).status_code == 422
        if mode == "performance":
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                timings = sorted(executor.map(prediction, range(100)))
            p95 = timings[94]
            print({"p95_seconds": p95, "mean_seconds": statistics.mean(timings)})
            assert p95 < float(os.getenv("MAX_P95_SECONDS", "2")), "Latency gate failed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("mode", choices=["smoke", "api", "integration", "performance", "security"])
    parser.add_argument("--version")
    args = parser.parse_args()
    check(args.url, args.mode, args.version)
