# Production Launch Checklist (MVP)

This checklist covers the minimum steps to safely deploy the control-plane on
AWS and the data-plane in customer Kubernetes clusters.

## Control-plane (AWS / ECS Fargate)

- [ ] Control-plane and event-processor images pushed to ECR
- [ ] ECS task definitions updated to new image tags
- [ ] Security groups allow outbound to MSK (if using Kafka) / RDS / ElastiCache
- [ ] MSK bootstrap reachable from ECS subnets (Kafka mode only)
- [ ] SQS FIFO queue reachable and IAM policy attached (SQS mode only)
- [ ] RDS/Aurora reachable from ECS subnets
- [ ] ElastiCache reachable from ECS subnets
- [ ] HTTPS endpoint in place (ALB + certificate)
- [ ] `CLERK_JWKS_URL`, `CLERK_ISSUER`, `CLERK_AUDIENCE` configured
- [ ] `CONTROL_PLANE_ADMIN_TOKEN` set
- [ ] Data-plane tokens minted via admin API (DB-backed)
- [ ] `DATA_PLANE_LOG_POLLS=false` in production
- [ ] CloudWatch log groups created and retention set

## Data-plane (Customer Kubernetes)

- [ ] Helm values set:
  - [ ] `controlPlaneUrl` (HTTPS control-plane endpoint)
  - [ ] `dataPlaneTenantId` (Clerk org id)
  - [ ] `dataPlaneApiToken` (tenant token)
  - [ ] `trainingNamespace` (target namespace for Jobs)
- [ ] Job-launcher service account has RBAC to create Jobs/ConfigMaps
- [ ] Training job image is pullable from customer cluster
- [ ] Cluster has outbound network access to control-plane HTTPS endpoint

## Token onboarding (per tenant)

- [ ] Mint token via admin endpoint:
  - `POST /internal/admin/data-plane-tokens`
- [ ] Provide token to customer (Helm values)
- [ ] Verify `/internal/jobs` returns expected job list

## Validation (pre-launch)

- [ ] Submit a test job in the UI
- [ ] Confirm job appears in data-plane cluster
- [ ] Confirm logs/metrics flow to UI
- [ ] Confirm job cancellation deletes the job

## Optional but recommended

- [ ] Add alarms for ECS task restarts
- [ ] Add rate limiting on internal endpoints
- [ ] Run load test on `/internal/jobs` polling
