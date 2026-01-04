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


To start the cluster:
```bash
 minikube start
```


To run the full stack locally with Docker Compose:
```bash
docker-compose up  --build --force-recreate
# remove the unused job-launcher container in the local mac since it will be run in minikube
```
To bring down the local services:
```bash
docker-compose down -v
```

To build the (data plane) job launcher and training job in minikube:
```bash
eval $(minikube docker-env)
docker build -t ai-platform-job-launcher:latest ./job-launcher
docker build -t ai-platform-training-job:latest ./training-job

kubectl get pods  -n training-jobs
kubectl delete pod <pod id for job launcher>  -n training-jobs
```

To install the data plan with Helm:
```bash
 helm upgrade --install ai-platform-data-plane ./helm-data-plane -n training-jobs
```

To examine the job information in the DB:
```bash
docker exec -it ai-platform-d-postgres-1  psql -U postgres -d controlplane -c "SELECT * FROM jobs;"
docker exec -it ai-platform-d-postgres-1  psql -U postgres -d controlplane -c "SELECT * FROM job_events;"
docker exec -it ai-platform-d-postgres-1  psql -U postgres -d controlplane -c "SELECT * FROM job_state;"
```

To watch Kafka queue:
```bash
 docker exec -it kafka /opt/kafka/bin/kafka-console-consumer.sh  --bootstrap-server kafka:9092 --topic job-events --from-beginning
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
 cd frontend_full
 npm install
 npm start
```

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

