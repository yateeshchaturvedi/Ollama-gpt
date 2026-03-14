# Deployment Guide (Azure)

This guide covers two deployment options:

- `AKS` (recommended for production and multi-service workloads)
- `Azure App Service` (simpler, best for single-container web app workloads)

Your stack has multiple long-running services (`ollama`, `openwebui`, `ai-agent`, optional `slack-agent`), so `AKS` is the better production fit.

## 1. Prerequisites

- Azure subscription
- Azure CLI installed and logged in:
```bash
az login
az account set --subscription "<SUBSCRIPTION_NAME_OR_ID>"
```
- Docker installed
- `kubectl` and `helm` installed

## 2. Container Registry Setup (ACR)

```bash
az group create -n rg-ollama-gpt -l eastus
az acr create -n ollamagptacr -g rg-ollama-gpt --sku Standard
az acr login -n ollamagptacr
```

Build and push images from this repo:

```bash
docker build -t ollamagptacr.azurecr.io/ai-agent:latest ./agent
docker push ollamagptacr.azurecr.io/ai-agent:latest

docker pull ghcr.io/open-webui/open-webui:main
docker tag ghcr.io/open-webui/open-webui:main ollamagptacr.azurecr.io/openwebui:main
docker push ollamagptacr.azurecr.io/openwebui:main
```

For Ollama image (optional mirror):

```bash
docker pull ollama/ollama:latest
docker tag ollama/ollama:latest ollamagptacr.azurecr.io/ollama:latest
docker push ollamagptacr.azurecr.io/ollama:latest
```

## 3. Deploy to AKS (Recommended)

### 3.1 Create AKS Cluster

For CPU-only:

```bash
az aks create \
  -g rg-ollama-gpt \
  -n aks-ollama-gpt \
  --node-count 2 \
  --generate-ssh-keys \
  --attach-acr ollamagptacr
```

For GPU nodepool (NVIDIA):

```bash
az aks nodepool add \
  --resource-group rg-ollama-gpt \
  --cluster-name aks-ollama-gpt \
  --name gpunp \
  --node-count 1 \
  --node-vm-size Standard_NC4as_T4_v3
```

Fetch credentials:

```bash
az aks get-credentials -g rg-ollama-gpt -n aks-ollama-gpt
```

### 3.2 Create Namespace and Secrets

```bash
kubectl create namespace ollama-gpt
kubectl -n ollama-gpt create secret generic app-secrets \
  --from-literal=HF_TOKEN="<HF_TOKEN>" \
  --from-literal=GITHUB_TOKEN="<GITHUB_TOKEN>" \
  --from-literal=SLACK_BOT_TOKEN="<SLACK_BOT_TOKEN>" \
  --from-literal=SLACK_APP_TOKEN="<SLACK_APP_TOKEN>"
```

### 3.3 Kubernetes Manifests

Create a `k8s/` folder with:

- `ollama-deployment.yaml` (+ PVC + service)
- `openwebui-deployment.yaml` (+ service + ingress)
- `ai-agent-deployment.yaml`
- `slack-agent-deployment.yaml` (optional)
- `configmap.yaml` for non-secret env vars

Core mapping from your `.env`:

- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT_SECONDS`
- `OLLAMA_RETRIES`
- `MAX_TOOL_STEPS`
- `MAX_HISTORY`
- `LOG_LEVEL`
- `SLACK_ALLOWED_CHANNEL`
- `SLACK_REQUIRE_MENTION`
- `MAX_SLACK_REPLY_CHARS`
- `GITHUB_MONITOR_REPOS`
- `GITHUB_ALERT_CHANNEL`
- `GITHUB_ALERT_POLL_SECONDS`
- `GITHUB_DIGEST_REPOS`
- `GITHUB_DIGEST_CHANNEL`
- `GITHUB_DIGEST_HOUR`
- `GITHUB_DIGEST_MINUTE`
- `GITHUB_TZ_OFFSET_MINUTES`

Apply manifests:

```bash
kubectl apply -n ollama-gpt -f k8s/
```

### 3.4 Ingress (Open WebUI)

Install NGINX ingress:

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace
```

Then configure Ingress to route to `openwebui` service on port `8080`.

### 3.5 Verify

```bash
kubectl get pods -n ollama-gpt
kubectl get svc -n ollama-gpt
kubectl logs -n ollama-gpt deploy/slack-agent --tail=100
```

## 4. Deploy to Azure App Service

Important: App Service is better for a single web container. This stack is multi-service, so for full parity prefer AKS.

If deploying only `openwebui` (and hosting Ollama elsewhere):

### 4.1 Create App Service Plan + Web App (Container)

```bash
az appservice plan create \
  -g rg-ollama-gpt \
  -n asp-ollama-gpt \
  --is-linux \
  --sku P1v3

az webapp create \
  -g rg-ollama-gpt \
  -p asp-ollama-gpt \
  -n openwebui-prod-<unique> \
  -i ollamagptacr.azurecr.io/openwebui:main
```

### 4.2 Configure Registry Auth + App Settings

```bash
ACR_USER=$(az acr credential show -n ollamagptacr --query username -o tsv)
ACR_PASS=$(az acr credential show -n ollamagptacr --query passwords[0].value -o tsv)

az webapp config container set \
  -g rg-ollama-gpt \
  -n openwebui-prod-<unique> \
  --container-image-name ollamagptacr.azurecr.io/openwebui:main \
  --container-registry-url https://ollamagptacr.azurecr.io \
  --container-registry-user $ACR_USER \
  --container-registry-password $ACR_PASS
```

Set app settings:

```bash
az webapp config appsettings set \
  -g rg-ollama-gpt \
  -n openwebui-prod-<unique> \
  --settings OLLAMA_BASE_URL="http://<your-ollama-endpoint>:11434"
```

### 4.3 Verify

```bash
az webapp browse -g rg-ollama-gpt -n openwebui-prod-<unique>
az webapp log tail -g rg-ollama-gpt -n openwebui-prod-<unique>
```

## 5. Production Hardening Checklist

- Store secrets in Azure Key Vault (not in plain app settings)
- Enable Managed Identity and least-privilege access
- Configure autoscaling (AKS HPA / node autoscaler)
- Add persistent volumes for Ollama model cache
- Add centralized logging (Azure Monitor / Log Analytics)
- Add health probes and alerting
- Pin image tags (avoid mutable `latest` in production)
- Rotate all leaked tokens immediately

## 6. Recommended Path

- Use `AKS` for full stack deployment.
- Use `Azure App Service` only for `openwebui`-style single web workloads, with Ollama hosted separately.

