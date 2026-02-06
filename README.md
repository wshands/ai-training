# AI Platform - Control Plane + Data Plane

This repo contains a full, opinionated starting point for a SaaS AI training platform:

- control-plane/api/ – FastAPI API to submit training jobs
- control-plane/event-processor/ – Kafka consumer that persists job events and state
- control-plane/ui/ – React UI for jobs
- data-plane/ – Job launcher + training job runtime for customer clusters
- deploy/helm/ – Helm charts to deploy platform components
- deploy/terraform/control-plane/ – Terraform skeleton for AWS infra
- docker-compose.yml – Local dev stack (Kafka, Postgres, services)
- .github/workflows/ – CI workflow to build/push Docker images


To start the cluster:
```bash
 minikube start
```

To run the full stack locally with Docker Compose:
```bash
docker-compose up  --build --force-recreate
```

To bring down the local services:
```bash
docker-compose down -v
```

To build the control plane images:
```bash
# 1) Set vars
export REGION=us-west-2
export ACCOUNT_ID=230407893272
export ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# 2) Login to ECR
aws ecr get-login-password --region "$REGION" --profile AdministratorAccess-230407893272 | \
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
  -t 230407893272.dkr.ecr.us-west-2.amazonaws.com/ai-training/job-launcher:latest \
  -f data-plane/launcher/Dockerfile \
  --push .

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t 230407893272.dkr.ecr.us-west-2.amazonaws.com/ai-training/training-job:latest \
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
aws sso login --profile AdministratorAccess-230407893272
```

To login to ECR so you can push images to ECR:
```bash
aws ecr get-login-password --region us-west-2 --profile AdministratorAccess-230407893272 \
  | docker login --username AWS --password-stdin 230407893272.dkr.ecr.us-west-2.amazonaws.com
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
aws sso login --profile AdministratorAccess-230407893272
AWS_PROFILE=AdministratorAccess-230407893272 npm run deploy:terraform
```