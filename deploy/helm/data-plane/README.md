# Data-plane Helm chart

## Values files

Use the provided values files for local or EKS deployments:

```bash
helm upgrade --install ai-data-plane ./deploy/helm/data-plane \
  --namespace training-jobs --create-namespace \
  -f values-local.yaml
```

```bash
helm upgrade --install ai-data-plane ./deploy/helm/data-plane \
  --namespace training-jobs --create-namespace \
  -f values-prod.yaml
```

## Multiple data-plane deployments (local + prod)

If you want both a local data-plane and a prod data-plane running side by side,
install the chart twice with different release names and tokens. Using separate
namespaces avoids RBAC and ServiceAccount name collisions.

```bash
helm upgrade --install ai-training-local-agent ./deploy/helm/data-plane \
  --namespace training-jobs-local --create-namespace \
  -f values-local.yaml \
  --set-string jobLauncher.trainingNamespace=training-jobs-local \
  --set-string jobLauncher.dataPlaneApiToken="local-dev-token" \
  --set-string jobLauncher.dataPlaneTenantId="org_local" \
  --set-string jobLauncher.controlPlaneUrl="http://host.docker.internal:8000"
```

```bash
helm upgrade --install ai-training-prod-agent ./deploy/helm/data-plane \
  --namespace training-jobs-prod --create-namespace \
  -f values-prod.yaml \
  --set-string jobLauncher.trainingNamespace=training-jobs-prod \
  --set-string jobLauncher.dataPlaneApiToken="prod-token" \
  --set-string jobLauncher.dataPlaneTenantId="org_prod" \
  --set-string jobLauncher.controlPlaneUrl="https://api.aitrainops.com"
```

## Publish a public Helm repo (GitHub Pages)

Use a separate repo (e.g. `wshands/aitrainops-charts`) with GitHub Pages enabled on the
`gh-pages` branch.

1) Create the charts repo and enable Pages

- Repo: `wshands/aitrainops-charts`
- Settings → Pages → Source: `gh-pages` branch
- Public URL: `https://wshands.github.io/aitrainops-charts`

2) Clone the charts repo locally

```bash
git clone git@github.com:wshands/aitrainops-charts.git ~/code/aitrainops-charts
```

3) Package and publish the chart

```bash
export CHARTS_REPO_DIR="$HOME/code/aitrainops-charts"
export CHARTS_REPO_URL="https://wshands.github.io/aitrainops-charts"
./scripts/helm-publish.sh
```

Run the script from the repo root so relative paths resolve correctly.

4) Install from the public repo

```bash
helm repo add aitrainops https://wshands.github.io/aitrainops-charts
helm repo update
helm install aitrainops-agent aitrainops/ai-training-data-plane \
  --namespace training-jobs --create-namespace \
  --set jobLauncher.dataPlaneTenantId=org_123 \
  --set jobLauncher.dataPlaneApiToken=token_abc
```

## GitHub Actions publishing (optional)

There is a workflow that packages and publishes the chart when:
- a `chart-*` tag is pushed, or
- `deploy/helm/data-plane/Chart.yaml` changes on `main`/`develop`.

Requirements:
- Add a repo secret `CHARTS_REPO_TOKEN` with permission to push to
  `wshands/aitrainops-charts` (gh-pages branch).
