#!/usr/bin/env bash
# Orchestrate deployment from hosted CI; execute endpoint gates inside the private VNet.
set -euo pipefail
: "${RG:?}" "${ACR_NAME:?}" "${IMAGE_REPOSITORY:?}" "${BUILD_ID:?}" "${APP_NAME:?}" "${ENVIRONMENT_NAME:?}"
az extension add --name containerapp --upgrade --yes
IDENTITY=$(az identity show -g "$RG" -n mlops-acr-reader --query id -o tsv)
DIGEST=$(az acr repository show -n "$ACR_NAME" --image "$IMAGE_REPOSITORY:$BUILD_ID" --query digest -o tsv)
IMAGE="$ACR_NAME.azurecr.io/$IMAGE_REPOSITORY@$DIGEST"
if [[ "${CHECK_ONLY:-false}" != true ]]; then
  az containerapp identity assign -g "$RG" -n "$APP_NAME" --user-assigned "$IDENTITY" -o none
  az containerapp registry set -g "$RG" -n "$APP_NAME" --server "$ACR_NAME.azurecr.io" --identity "$IDENTITY" -o none
  az containerapp ingress update -g "$RG" -n "$APP_NAME" --target-port 8000 -o none
  az containerapp update -g "$RG" -n "$APP_NAME" --image "$IMAGE" --revision-suffix "b$BUILD_ID" -o none
fi
FQDN=$(az containerapp show -g "$RG" -n "$APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)
JOB="mlops-check-$ENVIRONMENT_NAME-b$BUILD_ID"
if [[ "${CHECK_ONLY:-false}" == true ]]; then JOB="mlops-monitor-b${MONITOR_RUN_ID:?}"; fi
az containerapp job create -g "$RG" -n "$JOB" --environment mlops-environment-westus2 --trigger-type Manual \
  --replica-timeout 600 --replica-retry-limit 0 --replica-completion-count 1 --parallelism 1 \
  --image "$IMAGE" --cpu .5 --memory 1Gi --mi-user-assigned "$IDENTITY" \
  --registry-server "$ACR_NAME.azurecr.io" --registry-identity "$IDENTITY" \
  --command /venv/bin/python --args /service/scripts/cloud_checks.py \
  --env-vars "ENDPOINT=https://$FQDN" "MODEL_VERSION=$BUILD_ID" -o none
EXECUTION=$(az containerapp job start -g "$RG" -n "$JOB" --query name -o tsv)
for attempt in $(seq 1 60); do
  STATUS=$(az containerapp job execution list -g "$RG" -n "$JOB" --query "[?name=='$EXECUTION'].properties.status | [0]" -o tsv)
  echo "Private release checks: $STATUS"
  case "$STATUS" in
    Succeeded) mkdir -p artifacts; printf '{"app":"%s","version":"%s","image":"%s","execution":"%s","status":"Succeeded"}\n' "$APP_NAME" "$BUILD_ID" "$IMAGE" "$EXECUTION" > "artifacts/release-$ENVIRONMENT_NAME.json"; exit 0 ;;
    Failed) echo '##vso[task.logissue type=error]Private endpoint checks failed; inspect Container App job execution logs.'; exit 1 ;;
  esac
  sleep 10
done
echo '##vso[task.logissue type=error]Private endpoint checks timed out.'
exit 1
