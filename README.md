# AI Platform - Control Plane + Data Plane

Open-source control plane for running and governing ML training jobs across teams on shared GPU clusters. Training runs in your own Kubernetes cluster; the control plane tracks state, logs, metrics, and run history.

This repo contains:

- control-plane/api/ – FastAPI API to submit training jobs
- control-plane/event-processor/ – Kafka consumer that persists job events and state
- control-plane/ui/ – React UI for jobs
- data-plane/ – Job launcher + training job runtime for customer clusters
- deploy/helm/ – Helm charts to deploy platform components
- deploy/terraform/control-plane/ – Terraform skeleton for AWS infra
- docker-compose-kafka.yml – Local dev stack (Kafka, Postgres, services)
- .github/workflows/ – CI workflows to build/push Docker images

## Docs

- `docs/overview.md` — platform overview and MVP scope
- `docs/architecture-patterns.md` — implemented architecture and design patterns in code
- `docs/rbac.md` — role-based access control (roles + endpoint guards)
- `docs/job-queueing.md` — queue semantics, leases, retries
- `docs/audit-log.md` — audit log + export (job events + admin actions)
- `docs/threat-model.md` — MVP threat model and security boundaries
- `docs/third-party-services.md` — why/how external services are used (Cloudflare, Formspree, Clerk, Stripe, etc.)

## CI setup checklist

- [ ] Apply IAM OIDC stack: `deploy/terraform/iam-ci/`
- [ ] Set GitHub Secrets:
  - `AWS_ROLE_ARN` (ECR builds)
- [ ] Set GitHub Variables:
  - `AWS_REGION`
- [ ] Optional helper script to set GitHub secrets/variables:
  - `scripts/setup-github-ci.sh`


To start the cluster:
```bash
 minikube start
```

To run the full stack locally with Docker Compose (Kafka):
```bash
docker compose -f docker-compose-kafka.yml up --build --force-recreate
```

One-command local run script (macOS):
```bash
./scripts/run-ai-training-local.sh up --bus sqs
```

Useful script commands:
```bash
./scripts/run-ai-training-local.sh status --bus sqs
./scripts/run-ai-training-local.sh logs --bus sqs control-plane
./scripts/run-ai-training-local.sh down --bus sqs --volumes
```

macOS DNS reset helper:
```bash
./scripts/reset-macos-dns.sh
```

Optional alias (add to `~/.zshrc`):
```bash
alias dns-reset='/Volumes/CodeDevelopment/ai-training/scripts/reset-macos-dns.sh'
```

To bring down the local services:
```bash
docker compose -f docker-compose-kafka.yml down -v
```

To build the control plane images:
```bash
# 1) Set vars
export REGION=us-west-2
export ACCOUNT_ID=<your-aws-account-id>
export ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# 2) Login to ECR
aws ecr get-login-password --region "$REGION" --profile "$AWS_PROFILE" | \
  docker login --username AWS --password-stdin "$ECR_BASE"

# 3) Create repos if they don't exist
aws ecr describe-repositories --region "$REGION" \
  --repository-names ai-training-control-plane ai-training-event-processor >/dev/null 2>&1 || \
aws ecr create-repository --region "$REGION" --repository-name ai-training/control-plane

aws ecr describe-repositories --region "$REGION" \
  --repository-names ai-training-event-processor >/dev/null 2>&1 || \
aws ecr create-repository --region "$REGION" --repository-name ai-training/event-processor
```

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t "$ECR_BASE/ai-training/event-processor:latest" \
  -f control-plane/event-processor/Dockerfile --push .
```

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t "$ECR_BASE/ai-training/control-plane:latest" \
  -f control-plane/api/Dockerfile.prod --push .
```

CI/CD note:
- `.github/workflows/build-and-push-ecr.yml` builds and pushes control-plane + event-processor images to ECR on `main`/`develop` (OIDC).
- `.github/workflows/build-and-push-dockerhub.yml` builds and pushes data-plane images to DockerHub (public/test images).
- `deploy/terraform/iam-ci/` provisions GitHub OIDC roles for CI (ECR build role).
  - See `deploy/terraform/iam-ci/README.md` for required GitHub secrets and variables.

Tests note:
- `tests/test_retry_integration.py` uses Testcontainers and requires Docker to be running.
- Install dev dependencies before running tests: `pip install -r requirements-dev.txt`.

## AWS deploy scripts

- `scripts/deploy-ai-training-to-aws.sh`
  - Runs `terraform init` + guarded secret import + `terraform apply`.
  - Runs `scripts/setup-github-ci.sh` to sync the ECR role ARN into GitHub secrets.
  - Runs UI deploy using Terraform outputs.
  - Prints a summary (API/UI URLs, ALB DNS, UI bucket, CloudFront ID).
  - Run from anywhere; paths are resolved relative to the script location.
  - Optional flags:
    - `SKIP_GH_SETUP=1` to skip GitHub secrets/vars sync.
    - `SKIP_UI_DEPLOY=1` to skip UI deployment.
    - `POSTGRES_DSN_SECRET_NAME=...` to override the secret name.

- `scripts/destroy-ai-training-aws.sh`
  - Prompts for confirmation.
  - Removes the Postgres DSN secret from Terraform state (so destroy can proceed).
  - Empties the UI bucket (including versions + delete markers).
  - Runs `terraform destroy`.
  - Run from anywhere; paths are resolved relative to the script location.

Postgres snapshot restore (optional):
- `postgres_final_snapshot_enabled = true` will create a final snapshot on destroy.
- `postgres_snapshot_identifier = "rds:..."` restores from a snapshot on apply.
- When restoring from a snapshot, `db_name`, `username`, and `password` are ignored by AWS.

To check the terraform stack (AWS services for control plane):
```bash
aws ecs describe-services \
  --region us-west-2 \
  --cluster ai-platform-control-plane \
  --services control-plane
```

Kafka/MSK auth note (IAM / serverless):
- Set `KAFKA_SECURITY_PROTOCOL=SASL_SSL` and `KAFKA_SASL_MECHANISM=AWS_MSK_IAM`.
- Ensure the task role has MSK permissions and `AWS_REGION` or `AWS_DEFAULT_REGION` is set (used to sign tokens).
- If using SCRAM instead, set `KAFKA_SASL_MECHANISM=SCRAM-SHA-512` plus `KAFKA_SASL_USERNAME`/`KAFKA_SASL_PASSWORD`.

To build the (data plane) job launcher and training job in minikube:
```bash
eval $(minikube docker-env)
docker build -f data-plane/launcher/Dockerfile -t ai-platform-job-launcher:latest .
docker build -f data-plane/training-job/Dockerfile -t ai-platform-training-job:latest .
```


To build a multi-platform image for Mac or ECR:
```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ${ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/ai-training/job-launcher:latest \
  -f data-plane/launcher/Dockerfile \
  --push .

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ${ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/ai-training/training-job:latest \
  -f data-plane/training-job/Dockerfile \
  --push .
```

To delete old training jobs
```bash
kubectl get jobs,pods -n training-jobs -o name \                 
  | grep '^.*/train-' \      
  | xargs kubectl delete -n training-jobs

kubectl get pods  -n training-jobs
```

To install the data plane with Helm:
```bash
helm upgrade --install ai-training-data-plane ./deploy/helm/data-plane \
  --namespace training-jobs --create-namespace \
  -f ./deploy/helm/data-plane/values-local.yaml
```

To uninstall the data plane:
```bash
 helm uninstall ai-training-data-plane --namespace training-jobs
```

To examine the job information in the DB:
```bash
docker exec -it ai-training-postgres-1  psql -U postgres -d controlplane -c "SELECT * FROM jobs;"
docker exec -it ai-training-postgres-1  psql -U postgres -d controlplane -c "SELECT * FROM job_events;"
docker exec -it ai-training-postgres-1  psql -U postgres -d controlplane -c "SELECT * FROM job_state;"
```

To watch Kafka queue:
```bash
 docker exec -it kafka /opt/kafka/bin/kafka-console-consumer.sh  --bootstrap-server kafka:9092 --topic job-events --from-beginning
```
To test Redis:
```bash
docker exec -it redis redis-cli PUBLISH job_events:testjob '{"event_type":"JOB_LOG","job_id":"testjob","message":"hello from redis"}'
```

To monitor Redis:
```bash
docker exec -it redis redis-cli ping
docker exec -it redis redis-cli MONITOR
```

To submit a training request manually:
```bash
curl -X POST http://localhost:8000/jobs/train \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "foo",
    "dataset_id": "bar",
    "epochs": 5,
    "batch_size": 8,
    "lr": 0.01
  }'
```

To start UI not using VSCode:
```bash
 cd control-plane/ui
 npm install
 npm start
```

Auth note (Clerk):
- If password sign-in hangs on `/login/factor-two`, disable **Client Trust** in Clerk (User & authentication → Password) for dev.
- Test emails (`+clerk_test`) use code `424242` for email verification flows.
- Roles/permissions (RBAC):
  - Create custom org roles in the Clerk dashboard (Organizations → Roles & Permissions → Role Sets):
    - `operator` and `viewer` (Clerk stores them as `org:operator`, `org:viewer`).
  - Note: the current codebase enforces **roles only** (admin/operator/viewer). Clerk permissions are not yet used.
    - You can still define permissions in Clerk for future use, but they do not affect access today.
  - Assign roles to users from the org members page.

If using VSCode and Dockerfile.dev start debugging by picking the "UI + Attach backend (Docker)" (see .vscode/launch.json)

To see API:
```bash
 open http://localhost:8000/docs
```

To see UI Dashboard:
```bash
 open http://localhost:3000
```

To temporarily stop the cluster but keep data:
```bash
 minikube stop 
```

To bring down the cluster and delete all data:
```bash
 minikube delete
```


To test:
```bash
 pip install -r requirements-dev.txt
 pytest
```


To login using SSO:
```bash
aws sso login --profile "$AWS_PROFILE"
```

To login to ECR so you can push images to ECR:
```bash
aws ecr get-login-password --region us-west-2 --profile "$AWS_PROFILE" \
  | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com
```


To load UI into AWS S3 bucket for CloudFront:
```bash
cd control-plane/ui
rm -rf node_modules/.cache node_modules
npm ci
npm run build
aws s3 sync build/ s3://ai-training-ui-47c2098c --delete
aws cloudfront create-invalidation --distribution-id E2B3IF0DO03LIO --paths "/*"
```

To remove the existing postgres dsn secret so Terraform destroy will work:
```bash
terraform state rm aws_secretsmanager_secret.postgres_dsn
terraform destroy
```

To import the existing postgres dsn secret so Terraform apply will work:
```bash
terraform import aws_secretsmanager_secret.postgres_dsn ai-platform/postgres-dsn
terraform apply
```

To delete the UI bucket so Terraform destroy can run:
```bash
BUCKET=ai-training-ui-47c2098c

# delete all object versions
aws s3api list-object-versions \
  --bucket "$BUCKET" \
  --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
  --output json > /tmp/versions.json
aws s3api delete-objects --bucket "$BUCKET" --delete file:///tmp/versions.json

# delete all delete markers
aws s3api list-object-versions \
  --bucket "$BUCKET" \
  --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
  --output json > /tmp/delete-markers.json
aws s3api delete-objects --bucket "$BUCKET" --delete file:///tmp/delete-markers.json
```

To deploy the UI to AWS CloudFront using Terraform outputs:
```bash
cd control-plane/ui
aws sso login --profile "$AWS_PROFILE"
npm run deploy:terraform
```
