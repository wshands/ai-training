# Copilot instructions for AI coding agents

Purpose
- Provide concise, actionable guidance so an AI coding agent can be productive in this repo.

Big picture (one-paragraph)
- This repository implements an AI training platform with several cooperating services:
  - `control-plane` (FastAPI) - REST/WebSocket API, writes job state to the DB and publishes events to Kafka/Redis.
  - `event-processor` - consumes Kafka events and writes canonical events/state into the DB.
  - `job-launcher` - component that creates Kubernetes Batch Jobs to run training containers.
  - `training-job` - the containerized training workload run inside k8s jobs.
  - `frontend_full` / `ui-dashboard` - UI apps that call the control-plane REST API and open WS streams.
  Events flow: clients -> control-plane -> Kafka -> event-processor -> DB -> Redis pubsub -> frontend WS.

Key files to inspect first
- `control-plane/api/app/main.py` — request handling and WS streaming (see `submit_training_job` and WS handler).
- `control-plane/api/app/db.py` — persistence API: `persist_initial_job`, `fetch_jobs`, `fetch_job_events_since`.
- `control-plane/api/app/kafka_bus.py` — Kafka producer init and `send_event` usage.
- `control-plane/event-processor/event_processor.py` and `state_machine.py` — consumer side, event normalization.
- `data-plane/launcher/launcher.py` — Kubernetes job manifests and submit logic.
- `data-plane/training-job/training_job_runner.py` — entrypoint run by the training container.
- Root `docker-compose.yml` — quick local dev environment.
- `deploy/helm/control-plane` and `deploy/helm/data-plane` — k8s Helm manifests for production-like deploys.

Project-specific conventions and patterns
- Events are JSON objects and must include a `type` (or payload `event_type`). The control-plane expects `JOB_*` event names.
- DB stores canonical events; payloads are sometimes strings (JSON encoded) — callers should handle `isinstance(payload, str)` like `main.py` does.
- WebSocket streams are implemented via Redis pubsub channels named `job_events:{job_id}`.
- Use env names from `common/ai_training_common/config.py` (e.g., `REDIS_URL`, `TRAINING_IMAGE`, `CUSTOMER_KUBECONFIG`).
- FastAPI logging is configured at module import time (`setup_logging()` in `control-plane/api/app/main.py`).

Local developer workflows
- Start full local stack (recommended for integration work):
  - `docker compose up` (root `docker-compose.yml`).
- Control-plane local run (iterative edits): build the image or run inside Python venv pointing envs at local services; logs are useful: `docker compose logs -f control-plane`.
- Frontend: `cd frontend_full && npm install && npm start` (or `cd ui-dashboard && npm install && npm run dev`).

Debugging tips specific to this repo
- When investigating missing job state, follow the chain: API handler (`submit_training_job`) -> `persist_initial_job` -> `send_event` -> Kafka topic -> `event-processor` write to DB -> Redis publish.
- If WebSocket clients don't receive messages, check Redis pub/sub channels: `job_events:{job_id}` and ensure `event_processor` or other publishers call `PUBLISH`.
- Check Kafka locally via composed Kafka UI (if present) or container logs for `event-processor`.

Making changes / PR guidance
- Keep changes minimal and focused. For API/DB changes update `control-plane/api/app/db.py` and corresponding SQL migration (if present).
- When modifying event shapes, update both producer (`control-plane` or callers) and consumer (`event-processor`) and add a short example event in tests or README.

If you need clarification
- Ask which component to focus on and whether to prefer docker-compose local runs or Helm-based clusters for testing.

End of file
