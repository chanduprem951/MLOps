# Verification and deployment status

Updated 7 October 2026, Asia/Kolkata.

## Verified repairs

- Private Azure DevOps project: Azure ML End-to-End MLOps in edukrondevops. Updated source, tests and notes are published.
- Cloud run 85 (20261007.5) PASSED: Python 3.14 dependency installation, code/data/dependency validation, eight unit tests, training/evaluation/model quality, FastAPI contract tests, packaging, Docker build, real container readiness/prediction/version and strict HIGH/CRITICAL Trivy image gate. Both model evidence and Python package artifacts were published.
- Prior runs 81–84 failed dependency or Debian image vulnerabilities. These findings were remediated through dependency updates and replacing the serving runtime with Chainguard Wolfi Python, without suppressing vulnerability findings.
- Local eight unit tests, Ruff, pip check and runtime pip-audit pass. Bandit reports zero high/medium findings.
- Live local HTTP smoke, integration, API, performance and negative-input security contract checks passed. Performance p95 was 0.082 seconds for 100 requests with ten workers; this is a local result, not an Azure capacity guarantee.
- Fixed constant-feature PSI drift detection, monitoring Python mismatch, missing private blob container provisioning, bootstrap port mismatch and YAML ACR placeholder shadowing UI configuration. Serving checks model SHA256 against its release manifest before deserialization.
- Cloud run 86 passed the release-preflight revision and strict image scan. Cloud run 88 (20261007.8) PASSED the final revision. CI completed successfully in 2m 37s; development, staging, approval and production were explicitly skipped because deploy=false. Development, staging, approval and production stages now appear in CI-only runs, then skip explicitly until deploy=true. Release jobs are compiled only on activation so CI does not require an unconfigured private agent pool.

## Deployment and monitoring activation

- Training pipeline definition 15 and monitoring definition 16 exist. Monitoring is disabled until a verified production version and approved monitoring batch are configured.
- Environments ml-dev, ml-staging and ml-prod exist. Production now names Bharath K (giftzee.online@gmail.com) directly as reviewer. Self-approval remains disabled pending action-time confirmation of the requested temporary demo override.
- Resource group rg-mlops-demo exists in East US. Infrastructure run 89 created ACR edukronmlopsc2383f, storage account edukronmlopsc2383f with private ml-data container, mlops-logs and mlops-vnet. Its first attempt failed because the resource-group identity cannot register Microsoft.App at subscription scope. The owner registered Microsoft.App; registration is verified Registered, and a retry exposed East US capacity rejection. Run 90 completed infrastructure after moving the app environment to West US 2, as recorded below.
- azure-mlops-wif is saved using workload identity federation and Contributor at rg-mlops-demo. Only training pipeline 15 and monitoring pipeline 16 are authorized; all-pipelines access is disabled. Live AzureCLI authentication succeeded.
- Pipeline variables are set: acrName and dataStorageAccount both edukronmlopsc2383f; releaseApprovers giftzee.online@gmail.com.
- Owner granted mlops-acr-reader identity AcrPull only on this registry. The pipeline identity has Storage Blob Data Contributor only on this account's ml-data container. No subscription role was granted to the pipeline.
- Infrastructure run 90 (20261007.10) PASSED in 8m 43s. Internal-only environment mlops-environment-westus2 and VNet mlops-vnet-westus2 are in West US 2, after East US capacity rejection. Private DNS and mlops-iris-dev/staging/prod bootstrap apps exist. Azure ML workspace mlops-workspace provisioning state is Succeeded. The failed East US environment was deleted; its unused VNet is retained pending cleanup.
- CD and monitoring orchestration use hosted agents and launch endpoint checks as Container Apps jobs inside the private application network. Docker includes the endpoint checker and httpx. No private Azure DevOps agent pool is required.
- Metric definitions were verified. Enabled alerts: mlops-dev-cpu, mlops-staging-cpu and mlops-prod-cpu (mean CPU >450 million nanocores for five minutes), plus mlops-prod-api-5xx (>5 selected 5xx responses in five minutes). Action group mlops-operations uses the user's Gmail.
- Public Iris demonstration training CSV (150 validated labeled rows) is uploaded without overwrite to training/2026-10-07/iris.csv. trainingBlob points to this versioned source; it is demonstration data, not captured production traffic.
- Full release run 91 (20261007.11) uses deploy=true and retrain=true. CI PASSED in 5m 6s, including code/data/dependency, eight unit tests, approved-data retraining, quality, API, packaging, actual Docker serving, strict image security, ACR push and Azure ML registration. Model iris-classifier version 91 exists. Image digest is sha256:c64847d5ba41bf8ba5d016c3d6d401aef985f76113b4e33236d959bde4115642. Development PASSED in 4m 8s; private checker execution mlops-check-ml-dev-b91-vz0yfok is Succeeded. Staging PASSED in 3m 52s with revision mlops-iris-staging--b91 and the same image digest. The private checker execution is mlops-check-ml-staging-b91-aro2n21. Run 91 is waiting at stage 27 ManualValidation; production has not started.
- User requested temporary demo automatic approval with the same Gmail address. A default-off demoAutoApproval parameter is prepared locally, pending the action-time confirmation required for publishing the approval change. The production environment check remains unchanged.
- ACR publication and model registration have executed successfully. Private serving deployment, scheduled monitoring and automated retraining outcomes must be verified separately; production is not claimed complete while approval is pending.



## Current release handoff

CI, development and staging have passed. Temporary demo auto-approval is prepared locally but has not been published or enabled. The action-time confirmation is pending. After confirmation, publish the default-off demoAutoApproval parameter and queue a fresh release with deploy=true, retrain=true and demoAutoApproval=true; run 91 already compiled its manual approval steps and cannot use a later YAML change. Temporarily allow Bharath K to approve the ml-prod check, approve the verified demo release and restore requester self-approval to disabled after production tests pass. Only then pin monitoring to the actual production Build ID, enable pipeline 16 and run its checks. Do not use registered version 91 as production evidence until it has actually been promoted.
