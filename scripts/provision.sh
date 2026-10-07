#!/usr/bin/env bash
# Run after az login; requires Contributor and permission to assign AcrPull.
set -euo pipefail
: "${AZURE_SUBSCRIPTION:?Set subscription ID}"
: "${ACR_NAME:?Set globally unique lowercase registry name}"
: "${STORAGE_NAME:?Set globally unique storage name}"
: "${ALERT_EMAIL:?Set operations alert email}"
LOCATION=${LOCATION:-eastus}
RG=${RG:-rg-mlops-demo}
az account set --subscription "$AZURE_SUBSCRIPTION"
az extension add --name containerapp --upgrade --yes
az extension add --name ml --upgrade --yes
for provider in Microsoft.App Microsoft.OperationalInsights Microsoft.MachineLearningServices Microsoft.ContainerRegistry Microsoft.Insights; do
  az provider register --namespace "$provider" --wait
done
az group create -n "$RG" -l "$LOCATION"
az acr create -g "$RG" -n "$ACR_NAME" --sku Basic --admin-enabled false
az storage account create -g "$RG" -n "$STORAGE_NAME" -l "$LOCATION" --sku Standard_LRS --allow-blob-public-access false --min-tls-version TLS1_2
# The provisioning operator needs Storage Blob Data Contributor on this account.
az storage container create --auth-mode login --account-name "$STORAGE_NAME" --name ml-data --public-access off
az monitor log-analytics workspace create -g "$RG" -n mlops-logs -l "$LOCATION"
LOG_ID=$(az monitor log-analytics workspace show -g "$RG" -n mlops-logs --query customerId -o tsv)
LOG_KEY=$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n mlops-logs --query primarySharedKey -o tsv)
az network vnet create -g "$RG" -n mlops-vnet --address-prefix 10.42.0.0/16 --subnet-name apps --subnet-prefix 10.42.0.0/23
az network vnet subnet update -g "$RG" --vnet-name mlops-vnet -n apps --delegations Microsoft.App/environments
az network vnet subnet create -g "$RG" --vnet-name mlops-vnet -n agents --address-prefixes 10.42.2.0/24
SUBNET_ID=$(az network vnet subnet show -g "$RG" --vnet-name mlops-vnet -n apps --query id -o tsv)
az containerapp env create -g "$RG" -n mlops-environment -l "$LOCATION" --infrastructure-subnet-resource-id "$SUBNET_ID" --internal-only true --logs-workspace-id "$LOG_ID" --logs-workspace-key "$LOG_KEY"
unset LOG_KEY
DOMAIN=$(az containerapp env show -g "$RG" -n mlops-environment --query properties.defaultDomain -o tsv)
PRIVATE_IP=$(az containerapp env show -g "$RG" -n mlops-environment --query properties.staticIp -o tsv)
VNET_ID=$(az network vnet show -g "$RG" -n mlops-vnet --query id -o tsv)
az network private-dns zone create -g "$RG" -n "$DOMAIN"
az network private-dns link vnet create -g "$RG" -z "$DOMAIN" -n mlops-private-dns --virtual-network "$VNET_ID" --registration-enabled false
az network private-dns record-set a add-record -g "$RG" -z "$DOMAIN" -n '*' --ipv4-address "$PRIVATE_IP"
az network private-dns record-set a add-record -g "$RG" -z "$DOMAIN" -n '@' --ipv4-address "$PRIVATE_IP"
az ml workspace create -g "$RG" -n mlops-workspace -l "$LOCATION"
az identity create -g "$RG" -n mlops-acr-reader
IDENTITY=$(az identity show -g "$RG" -n mlops-acr-reader --query id -o tsv)
PRINCIPAL=$(az identity show -g "$RG" -n mlops-acr-reader --query principalId -o tsv)
ACR_ID=$(az acr show -g "$RG" -n "$ACR_NAME" --query id -o tsv)
az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID"
# Bootstrap apps with Microsoft's sample. The first release replaces this with the verified ML image.
# INTERNAL ingress: expose through an approved private gateway/VPN before live endpoint gates.
for env in dev staging prod; do
  # External here means outside the app environment but ONLY on the private VNet ILB.
  az containerapp create -g "$RG" -n "mlops-iris-$env" --environment mlops-environment --image mcr.microsoft.com/k8se/quickstart:latest --user-assigned "$IDENTITY" --registry-server "$ACR_NAME.azurecr.io" --registry-identity "$IDENTITY" --ingress external --target-port 80 --min-replicas 1 --max-replicas 3 --cpu .5 --memory 1Gi --revisions-mode single
done
az monitor action-group create -g "$RG" -n mlops-operations --short-name mlops --action email operations "$ALERT_EMAIL"
GROUP_ID=$(az monitor action-group show -g "$RG" -n mlops-operations --query id -o tsv)
for env in dev staging prod; do
  APP_ID=$(az containerapp show -g "$RG" -n "mlops-iris-$env" --query id -o tsv)
  az monitor metrics alert create -g "$RG" -n "mlops-$env-cpu" --scopes "$APP_ID" --condition 'avg UsageNanoCores > 450000000' --window-size 5m --evaluation-frequency 1m --action "$GROUP_ID" --description 'Sustained CPU pressure: investigate API latency and scale'
done
echo 'Provisioned private services. Configure private agent connectivity, API gateway authentication, role scopes, pipeline variables and approvals as documented.'
