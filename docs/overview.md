# AI Training Platform – Overview

## What it is
AiTrainOps is a control‑plane + data‑plane platform for running GPU training jobs in a customer’s cloud while keeping centralized orchestration, observability, and auditability in a vendor‑hosted control‑plane. Customers keep data and compute inside their own AWS account/VPC, while the vendor provides scheduling, job lifecycle management, live logs/metrics, and a web UI.

## Core goals
- **Run training jobs in customer VPCs** without data egress.
- **Provide centralized control and visibility** across clusters and teams.
- **Keep operational overhead low** with a lightweight data‑plane agent.
- **Support multi‑tenant SaaS** with secure isolation.

## Architecture at a glance

### Control‑plane (vendor AWS)
- **FastAPI API** for job submission, status, events, and WebSocket streams.
- **Postgres** stores job metadata, state projections, and event history.
- **Admin audit log** captures token mints/revokes and retention changes.
- **Event bus** for job lifecycle events (SQS FIFO by default; Kafka/MSK optional).
- **Redis** fan‑out for WebSocket live updates.
- **React UI** for job lists, detail, logs, metrics, and admin operations.

### Data‑plane (customer AWS / Kubernetes)
- **Job‑launcher** polls for work, claims jobs, and creates Kubernetes Jobs.
- **Training job container** emits lifecycle, logs, and metrics back to the control‑plane.
- **Helm chart** makes deployment simple for customer clusters.

## Job lifecycle flow
1) User submits a job via UI or API.
2) Control‑plane persists metadata and publishes `JOB_SUBMITTED` to the event bus.
3) Event‑processor stores events and updates state projections in Postgres.
4) Job‑launcher claims ready jobs and starts Kubernetes Jobs in the customer cluster.
5) Training jobs emit events/logs/metrics to the control‑plane.
6) UI receives live updates via WebSocket streams.

## Security model
- **User auth** via Clerk JWTs (org‑scoped tenancy).
- **RBAC** via Clerk org roles (admin/operator/viewer) enforced at the API and UI.
- **Data‑plane auth** via hashed, DB‑stored API tokens (admin‑minted).
- **Tenant isolation** enforced in control‑plane and data‑plane endpoints.
- **No data plane access to event bus**; only HTTPS to the control‑plane API.

## Deployment model
- Control‑plane runs in **vendor AWS** (ECS Fargate or EKS).
- Data‑plane runs in **customer AWS** (Kubernetes / EKS).
- Event bus can be **SQS FIFO** (default) or **Kafka/MSK** (optional).
- UI is hosted on **S3 + CloudFront** with optional custom domain.

## Why this approach
This architecture gives customers the benefits of a SaaS control‑plane without giving up control of their data or compute. It also keeps onboarding simple: install a Helm chart, mint a token, submit jobs.

## Ideal use cases
- Private ML training in regulated industries (biotech, finance, healthcare).
- Teams with Kubernetes + GPUs but no dedicated MLOps team.
- Orgs that need auditability, job history, and reliable orchestration.

## What’s included in the MVP
- Job submission + cancellation
- Event‑driven state tracking
- Live logs and metrics in the UI
- Multi‑tenant auth
- Data‑plane job launcher for Kubernetes
- Admin audit export (job events + admin actions)

## What’s next (roadmap)
- Token rotation + lifecycle policies
- Cost/GPU usage insights
- Advanced retry/queue policies

---

See also:
- `docs/architecture-overview.md`
- `docs/data-plane-auth.md`
- `docs/job-queueing.md`
