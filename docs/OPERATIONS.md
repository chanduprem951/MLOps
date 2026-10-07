# Azure setup and operating notes

## 1. Prerequisites and cost scope

Use organization `edukrondevops`, the private project `Azure ML End-to-End MLOps`, an Azure subscription with sufficient quota, and a selected supported region. Provisioning creates billable ACR, storage, Azure ML supporting resources, Log Analytics and three Container Apps. Infrastructure run 90 executed `scripts/provision_cd.sh` successfully. The live demo resources are billable; review subscription costs and configure a budget appropriate to continued operation.

Install Azure CLI from Microsoft, sign in with `az login`, then run the bash provisioning script from WSL or a Linux administrative runner. Set `AZURE_SUBSCRIPTION`, globally unique `ACR_NAME`, `STORAGE_NAME`, `ALERT_EMAIL`, and optionally `LOCATION` and `RG`. The script uses explicit subscription selection and never echoes storage/log shared keys. Contributor plus User Access Administrator (or equivalent scoped rights) are needed for managed-identity ACR role assignment.

For a business production deployment use separate resource groups/subscriptions, policies and identities for production. The demo shares a resource group/environment to keep setup smaller.

## 2. Configure Azure DevOps identity

Project settings -> Service connections -> New -> Azure Resource Manager -> workload identity federation. Name it `azure-mlops-wif`. Scope it to the required resource group, not the whole subscription. Authorize only these pipelines. Assign least-privilege rights for Container App updates, ACR pushes, Azure ML model registration and the selected storage container. Avoid PATs or client secrets in code. Creating a new federated identity or broader access requires an administrator's authorization.

For CD, `scripts/provision_cd.sh` creates VNet `mlops-vnet-westus2`, a delegated apps subnet, internal-only environment `mlops-environment-westus2` and wildcard private DNS. East US rejected environment creation due to regional capacity; the application network was moved to West US 2 while ACR/storage/AML remain East US. App ingress uses `external` to allow callers outside the app environment, but the environment's internal load balancer keeps it VNet-only. Microsoft-hosted agents orchestrate Azure operations; `scripts/deploy_cd.sh` launches release-test jobs within the private environment. Monitoring uses the same checker with CHECK_ONLY=true and a unique job per monitoring run, without changing the deployed revision. No private DevOps agent pool is required. Do not make ingress public to pass a test.

## 3. Pipeline variables

Set these in the training pipeline or an authorized variable group:

| Variable | Value / purpose |
|---|---|
| azureServiceConnection | `azure-mlops-wif` |
| resourceGroup | `rg-mlops-demo` or selected group |
| acrName | Actual globally unique registry name; set in pipeline UI variables |
| amlWorkspace | `mlops-workspace` |
| imageRepository | `iris-api` |
| dataStorageAccount | Actual approved sample/training storage account |
| trainingBlob | Immutable approved CSV path, e.g. `training/2026-10-07/iris.csv` |
| releaseApprovers | Azure DevOps account/group identities for human release approval |

For monitoring also set `monitoringEnabled=true` only after setup is verified, `productionModelVersion`, `baselineBlob` (`versions/<deployed-id>/baseline.csv`), `modelBlob` (`versions/<deployed-id>/model.joblib`), `monitoringBlob` (approved production batch), and `trainingPipelineId` (numeric training pipeline ID). Until enabled the scheduled workflow skips monitoring and retraining. Update deployed-version variables after every successful production release or rollback. Do not use the newest registered model as the production reference unless it was actually promoted.

The CI-safe provisioner creates private blob container `ml-data` through the ARM control plane. Blob upload/download uses Entra authentication and requires a data-plane role. The live pipeline identity has Storage Blob Data Contributor at the ml-data container only. The application managed identity has AcrPull at the dedicated registry only. Provider registration is performed by the subscription owner, never by broadening the pipeline identity. Enable appropriate retention/versioning and review artifact access for real datasets.

## 4. Create pipelines and approval resources

Training pipeline definition 15 uses `/azure-pipelines.yml`; monitoring definition 16 uses `/pipelines/monitoring.yml`. Run CI first with `deploy=false`. Monitoring is saved with processing Disabled: after the deployed-version variables and approved monitoring samples are verified, open its Settings, choose Enabled, and set `monitoringEnabled=true`.

Create environments `ml-dev`, `ml-staging`, `ml-prod`. On `ml-prod`, add Approvals and checks -> Approvals; assign the designated production reviewer, disable requester self-approval, set a review timeout. Restrict pipeline permissions to the training pipeline and apply an exclusive lock. Environment checks live outside YAML and should be controlled by the production resource owner. ManualValidation in YAML supplies an additional visible review stage.

Repositories -> main -> Branch policies: at least one reviewer, successful build validation using the CI pipeline, resolve comments, prevent direct unreviewed changes for normal development. Configure failure notifications and retention of release evidence. Grant the monitoring Build Service only permission to queue the selected training pipeline; `System.AccessToken` is ephemeral and passed through environment, never logged.

## 5. First release and service access

Run full CI and review the dependency and image scan findings. Resolve vulnerabilities by updating pins and rerunning tests; do not suppress findings to obtain a green build. Then run `deploy=true`. CI registers the model, uploads its baseline/manifest and pushes its image. Deployment resolves the Build-ID tag to a digest and verifies that `/ready` reports that exact Build ID.

The API does not implement end-user authentication itself. Keep internal ingress until a suitable private gateway or authenticated access layer exists. For public hosting configure an approved gateway or Container Apps authentication with Entra ID, rate limiting, TLS, scoped network controls and appropriate access policy. Propagate a test token through secret pipeline variables if the gateway requires bearer authentication. Restrict `/metrics` and model metadata to operators. Configure Container Apps readiness/liveness probes for `/ready` and `/health` and resource limits after workload testing.

## 6. Monitoring wiring

Container Apps environment logs go to `mlops-logs`. `scripts/configure_alerts.sh` configured three CPU alerts, a production 5xx alert and the Gmail action group. Supported metric names and dimensions were verified against the live resources. To review metric definitions use `az monitor metrics list-definitions --resource <app-resource-id>` and adjust thresholds for the chosen CPU quota. Additional scheduled Log Analytics alerts for missing readiness and application-specific errors remain an operational extension. Configure failed-run notifications on both pipelines.

Example KQL (verify table/field availability in your workspace):

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(15m)
| extend message = parse_json(Log_s)
| where isnotempty(message.status)
| summarize requests=count(), errors=countif(toint(message.status)>=500), p95_ms=percentile(todouble(message.duration_ms),95) by bin(TimeGenerated,5m), ContainerAppName_s
```

Scrape private `/metrics` through a Prometheus-compatible collector at a configured interval. Display request count, 5xx ratio, latency p95, readiness, replica restarts and prediction class/version mix. This repo emits metric data; it does not deploy the scraper or dashboard. Keep collector access private and credential-protected.

Upload approved production samples with the same four feature names; include `target` only when verified delayed labels are available. Daily monitoring uses PSI > 0.2 or labeled accuracy < 0.90. It fails on missing samples rather than pretending there is no drift. Use sufficient sample counts and tune drift thresholds to avoid false retraining. Scheduled time is 02:00 UTC / 07:30 Asia/Kolkata.

## 7. Retraining and model promotion

On drift, monitoring queues the training pipeline on main with `retrain=true` and `deploy=true`. Training downloads `trainingBlob`, an approved immutable dataset, rather than directly trusting production samples. Every quality/security/test gate and production approval is repeated. Add ingestion/label review to your business workflow before selecting the new dataset. Apply exclusive locks and a queue/deduplication policy to avoid retraining the same drift batch daily. This demo currently relies on operations to acknowledge the report and update dataset/baseline references.

Model registration may succeed while deployment fails. Registered is not synonymous with production. Azure ML Build ID, Docker digest, manifest and actual `/ready` version together identify the promoted release. Retain the preceding approved digest and associated model/baseline blobs.

## 8. Rollback

1. Stop additional promotion and capture failing release evidence.
2. Select the previous approved image digest from release records; never guess a tag.
3. Run `az containerapp update --resource-group <rg> --name mlops-iris-prod --image <acr>.azurecr.io/iris-api@sha256:<previous-approved-digest>`.
4. Run `python -m scripts.check_endpoint <production-url> smoke --version <previous-build-id>` from the private network.
5. Point monitoring variables to the restored model version and its baseline/model blobs. Record reason, author and incident link.

There is no automatic rollback or blue/green traffic routing in this scaffold. A failed smoke test stops the pipeline and requires the documented operator rollback. Expand to multiple revisions with controlled traffic when production requirements demand it.

## 9. Troubleshooting

- Hosted-agent parallelism unavailable: request Microsoft-hosted parallelism or use an authorized agent pool; do not disable validation.
- Service connection missing/not authorized: create scoped WIF connection, authorize the intended pipeline only.
- ACR image pull failure: check AcrPull assignment propagation and user-assigned identity configuration.
- Readiness timeout: verify private DNS/network, target port 8000, startup logs, model artifact and version.
- Model gate failure: inspect split/class representation, metric evidence and domain changes; do not lower threshold without review.
- Drift pipeline fails: check approved sample availability, numeric schema, current production baseline and sufficient sample count.
- Approval pending: designated reviewer checks release evidence; timeout rejects.

## Primary references

- Azure DevOps environment approvals: https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals?view=azure-devops
- Environments: https://learn.microsoft.com/en-us/azure/devops/pipelines/process/environments?view=azure-devops
- Container Apps CLI: https://learn.microsoft.com/en-us/cli/azure/containerapp?view=azure-cli-latest

Configuration and resource APIs may evolve; validate provisioning in the selected subscription and review actual pipeline outputs before claiming deployment success.

Chainguard Python runtime reference: https://edu.chainguard.dev/chainguard/containers/getting-started/languages-and-runtimes/python/

## Runtime remediation and release preflight

Training and monitoring use Python 3.14. The final runtime uses Chainguard Python with a pip-free virtual environment and nonroot execution. The builder asserts Python 3.14; a future latest-tag interpreter change deliberately stops the build for review. Strict HIGH/CRITICAL image scanning remains enabled and exports image-security.json even if the scan fails. Review and pin matched builder/runtime digests for production reproducibility.

The release checks acrName, dataStorageAccount and releaseApprovers before training. Set acrName in the pipeline UI; no YAML placeholder shadows that value. Provisioning bootstraps the Microsoft quickstart on port 80; deployment switches ingress to 8000 before installing the ML image. Endpoint tests run inside the private environment with the serving image's Python, httpx and checker scripts. The job must succeed before the next environment is promoted, and artifacts/release-<environment>.json records the exact digest, model version and execution name.

Run `provision=true, deploy=false` to provision infrastructure independently. The subscription owner must first register Microsoft.App and other required providers. Run `provision=false, deploy=true` for a release only after infrastructure succeeds. Approval defaults to manual; any temporary demo automation must be explicitly authorized, recorded and restored after the run.

