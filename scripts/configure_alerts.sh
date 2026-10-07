#!/usr/bin/env bash
# Scoped metrics and alert setup after the three apps exist.
set -euo pipefail
: "${RG:?}" "${ALERT_EMAIL:?}"
az monitor action-group create -g "$RG" -n mlops-operations --short-name mlops --action email operations "$ALERT_EMAIL" -o none
GROUP_ID=$(az monitor action-group show -g "$RG" -n mlops-operations --query id -o tsv)
for env in dev staging prod; do
  APP_ID=$(az containerapp show -g "$RG" -n "mlops-iris-$env" --query id -o tsv)
  az monitor metrics alert create -g "$RG" -n "mlops-$env-cpu" --scopes "$APP_ID" \
    --condition 'avg UsageNanoCores > 450000000' --window-size 5m --evaluation-frequency 1m \
    --action "$GROUP_ID" --description 'Sustained CPU pressure: investigate API latency and scale' -o none
done
az monitor metrics alert create -g "$RG" -n mlops-prod-api-5xx --scopes "$APP_ID" \
  --condition 'total Requests > 5 where statusCode includes 500 or 502 or 503 or 504' \
  --window-size 5m --evaluation-frequency 1m --action "$GROUP_ID" \
  --description 'Production API server errors exceeded five in five minutes' -o none
