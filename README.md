# AI Platform - Control Plane + Data Plane

This repo contains a full, opinionated starting point for a SaaS AI training platform:

- control-plane/api/ – FastAPI API to submit training jobs
- control-plane/event-processor/ – Kafka consumer that persists job events and state
- control-plane/ui/ – React UI for jobs
- data-plane/ – Job launcher + training job runtime for customer clusters
- deploy/helm/ – Helm charts to deploy platform components
- infra/aws/ – Terraform skeleton for AWS infra
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
