# AI Platform - Control Plane + Data Plane

This repo contains a full, opinionated starting point for a SaaS AI training platform:

- control-plane/ – FastAPI API to submit training jobs
- event-processor/ – Kafka consumer that persists job events and state
- job-launcher/ – Kafka consumer that launches Kubernetes Jobs
- training-job/ – Container image that runs training and emits events
- ui-dashboard/ – Next.js UI for jobs
- deploy/helm/ – Helm chart to deploy platform components
- k8s/data-plane/ – Example namespace + RBAC for customer cluster
- infra/aws/ – Terraform skeleton for AWS infra (VPC)
- docker-compose.yml – Local dev stack (Kafka, Postgres, services)
- .github/workflows/ – CI workflow to build/push Docker images
