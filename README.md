# Azure ML End-to-End MLOps

Private Azure DevOps project: https://dev.azure.com/edukrondevops/Azure%20ML%20End-to-End%20MLOps

A runnable educational Iris classifier, FastAPI prediction service, Azure Pipelines release workflow and scheduled drift/retraining workflow covering the requested 41 stages. The deployed model is bundled inside the same immutable image as its API, and also versioned in Azure ML. There is no separate Azure ML online endpoint in this design.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m ml.workflow all
python -m pytest -q
python -m ruff check .
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. Send `POST /predict` with:

```json
{"sepal_length":5.1,"sepal_width":3.5,"petal_length":1.4,"petal_width":0.2}
```

Docker: `docker build -t iris-api:local .`, then `docker run --rm -p 127.0.0.1:8000:8000 iris-api:local`.

## Documentation

- [All 41 stages and implementation notes](docs/STAGES.md)
- [Azure setup, approvals, monitoring and operational runbook](docs/OPERATIONS.md)
- [Implementation and verification status](docs/STATUS.md)

## Pipeline entry points

- `azure-pipelines.yml`: train, test, package and scan on main; `deploy=true` additionally registers and releases through dev, staging, approval and production. Default is CI only until Azure setup is complete.
- `pipelines/monitoring.yml`: daily production checks and drift evaluation; queues the training pipeline only when a drift threshold is breached. Production approval still applies to retrained models.
- `scripts/provision_cd.sh`: run with pipeline parameter `provision=true, deploy=false`; provisions the private application network and services. The owner separately grants the documented scoped data/pull roles. Creates billable resources.
- `scripts/configure_alerts.sh`: configures CPU and production 5xx alerts with the approved email action group.

The Iris dataset is a demonstration, not a business production model. Test-set scores use only 38 observations and are not evidence of generalization in a new domain. Adapt data schema, domain metrics and thresholds before business use.
