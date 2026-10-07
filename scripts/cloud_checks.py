"""Run release checks inside the private Container Apps network."""
import json
import os
import time

from check_endpoint import check


if __name__ == "__main__":
    url = os.environ["ENDPOINT"]
    version = os.environ["MODEL_VERSION"]
    for attempt in range(24):
        try:
            check(url, "smoke", version)
            break
        except Exception:
            if attempt == 23:
                raise
            time.sleep(5)
    for mode in os.getenv("CHECK_MODES", "integration,api,performance,security").split(","):
        check(url, mode, version)
        print(json.dumps({"release_gate": mode, "result": "passed", "model_version": version}), flush=True)
