#!/usr/bin/env bash
# Creates infrastructure using the already approved resource-group Contributor identity.
# RBAC assignments are deliberately performed separately by the resource owner.
set -euo pipefail
: "${ACR_NAME:?}" "${STORAGE_NAME:?}" "${RG:?}"
LOCATION=${LOCATION:-eastus}
APP_LOCATION=${APP_LOCATION:-westus2}
VNET_NAME="mlops-vnet-$APP_LOCATION"
az extension add --name containerapp --upgrade --yes
az extension add --name ml --upgrade --yes
echo 'Creating scoped ACR and storage resources'
az acr create -g "$RG" -n "$ACR_NAME" --sku Basic --admin-enabled false -o none
az storage account create -g "$RG" -n "$STORAGE_NAME" -l "$LOCATION" --sku Standard_LRS --allow-blob-public-access false --min-tls-version TLS1_2 -o none
az storage container-rm create -g "$RG" --storage-account "$STORAGE_NAME" --name ml-data --public-access off -o none
echo 'Creating private network and Log Analytics workspace'
az monitor log-analytics workspace create -g "$RG" -n mlops-logs -l "$LOCATION" -o none
LOG_ID=$(az monitor log-analytics workspace show -g "$RG" -n mlops-logs --query customerId -o tsv)
LOG_KEY=$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n mlops-logs --query primarySharedKey -o tsv)
echo "##vso[task.setsecret]$LOG_KEY"
az network vnet create -g "$RG" -n "$VNET_NAME" -l "$APP_LOCATION" --address-prefix 10.42.0.0/16 --subnet-name apps --subnet-prefix 10.42.0.0/23 -o none
az network vnet subnet update -g "$RG" --vnet-name "$VNET_NAME" -n apps --delegations Microsoft.App/environments -o none
SUBNET_ID=$(az network vnet subnet show -g "$RG" --vnet-name "$VNET_NAME" -n apps --query id -o tsv)
if ! az containerapp env show -g "$RG" -n mlops-environment-westus2 -o none 2>/dev/null; then
  echo 'Provisioning internal-only Container Apps environment (this may take several minutes)'
  az containerapp env create -g "$RG" -n mlops-environment-westus2 -l "$APP_LOCATION" --infrastructure-subnet-resource-id "$SUBNET_ID" --internal-only true --logs-workspace-id "$LOG_ID" --logs-workspace-key "$LOG_KEY" -o none
fi
STATE=$(az containerapp env show -g "$RG" -n mlops-environment-westus2 --query properties.provisioningState -o tsv)
[[ "$STATE" == Succeeded ]] || { echo "Container Apps environment is not ready: $STATE"; exit 1; }
unset LOG_KEY
DOMAIN=$(az containerapp env show -g "$RG" -n mlops-environment-westus2 --query properties.defaultDomain -o tsv)
PRIVATE_IP=$(az containerapp env show -g "$RG" -n mlops-environment-westus2 --query properties.staticIp -o tsv)
VNET_ID=$(az network vnet show -g "$RG" -n "$VNET_NAME" --query id -o tsv)
az network private-dns zone create -g "$RG" -n "$DOMAIN" -o none
if ! az network private-dns link vnet show -g "$RG" -z "$DOMAIN" -n mlops-private-dns -o none 2>/dev/null; then
  az network private-dns link vnet create -g "$RG" -z "$DOMAIN" -n mlops-private-dns --virtual-network "$VNET_ID" --registration-enabled false -o none
fi
az network private-dns record-set a add-record -g "$RG" -z "$DOMAIN" -n '*' --ipv4-address "$PRIVATE_IP" -o none
az network private-dns record-set a add-record -g "$RG" -z "$DOMAIN" -n '@' --ipv4-address "$PRIVATE_IP" -o none
if ! az ml workspace show -g "$RG" -n mlops-workspace -o none 2>/dev/null; then
  echo 'Creating Azure ML workspace'
  az ml workspace create -g "$RG" -n mlops-workspace -l "$LOCATION" -o none
fi
az identity create -g "$RG" -n mlops-acr-reader -o none
for env in dev staging prod; do
  if ! az containerapp show -g "$RG" -n "mlops-iris-$env" -o none 2>/dev/null; then
    az containerapp create -g "$RG" -n "mlops-iris-$env" --environment mlops-environment-westus2 --image mcr.microsoft.com/k8se/quickstart:latest --ingress external --target-port 80 --min-replicas 1 --max-replicas 3 --cpu .5 --memory 1Gi --revisions-mode single -o none
  fi
done
az identity show -g "$RG" -n mlops-acr-reader --query '{id:id,principalId:principalId}'
echo 'Infrastructure ready. Resource owner must grant the scoped ACR pull and blob-data roles before release.'
