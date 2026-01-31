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
  -f values-eks.yaml
```
