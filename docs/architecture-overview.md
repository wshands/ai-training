# Architecture Overview

This document describes the major components of the AI training platform, how
they interact, and how authentication and job lifecycle events flow through the
system.

## Components

### Control-plane

The control-plane is the system of record for jobs and user access. It exposes:

- Public REST API for the UI (`/jobs`, `/jobs/{id}`, `/jobs/{id}/events`)
- Internal endpoints for the data-plane (`/internal/jobs/claim`, `/internal/jobs`, `/internal/events`)
- WebSocket streams for live updates (`/ws/jobs/{job_id}`, `/ws/jobs`)

It is responsible for:

- Validating user identity (Clerk JWT)
- Creating job records and emitting submission/cancel events
- Enforcing tenant isolation
- Publishing events to Kafka
- Serving job/event queries to the UI

### Event-processor

The event-processor consumes Kafka events, validates them, and writes them to
Postgres. It also publishes updates to Redis for WebSocket fan-out.

Responsibilities:

- Validate and store job events
- Update job state projections (`job_state`)
- Enforce event schema constraints
- Prune old event history (optional retention)

### Data-plane (job-launcher + training-job)

The data-plane runs in the customer’s cluster. It never talks to Kafka directly
in production. Instead it:

- Polls the control-plane for submitted jobs
- Creates Kubernetes Jobs in the customer cluster
- Sends job lifecycle events back to the control-plane

The training job container emits metrics/logs via the control-plane HTTP ingest
API.

### Kafka

Kafka is the internal event bus for job lifecycle events. It is owned by the
control-plane environment (MSK in production).

### Postgres

Postgres stores job metadata and event history.

### Redis

Redis is used for pub/sub fan-out to WebSocket clients.

### Frontend (UI)

The UI is a React app using Clerk for authentication. It:

- Signs users in via Clerk
- Calls control-plane APIs with a Clerk JWT bearer token
- Subscribes to WebSocket streams for live updates

## Data flows

### Job submission (control-plane)

1) User signs in via Clerk.
2) UI calls `POST /jobs/train` with JWT.
3) Control-plane validates JWT and creates a job record.
4) Control-plane emits `JOB_SUBMITTED` to Kafka.
5) Event-processor stores the event and updates projections.

### Job execution (data-plane)

1) Job-launcher claims jobs via `POST /internal/jobs/claim`.
2) Control-plane atomically assigns ready jobs for the tenant.
3) Job-launcher emits `JOB_PENDING` via `POST /internal/events`.
4) Job-launcher creates a Kubernetes Job.
5) Training job emits lifecycle/log/metric events to control-plane.

### Live updates (UI)

1) UI connects to `ws://.../ws/jobs/{job_id}?token=...`.
2) Control-plane validates JWT and subscribes to Redis.
3) Event-processor publishes updates to Redis.
4) UI receives real-time events and updates charts/logs.

## Authentication & tenancy

### User auth (Clerk)

The control-plane validates JWTs from Clerk:

- `tenant_id` is derived from `org_id` if present
- if no org is active, `tenant_id` falls back to `sub`

The UI enforces org selection to ensure `org_id` is present.

### Data-plane auth

Internal endpoints are protected by a data-plane token and tenant scope:

- `Authorization: Bearer <token>`
- `X-Tenant-Id: <tenant_id>`
- `X-Agent-Id: <agent_id>` (for auditing)

Tokens are stored hashed in Postgres and minted via admin endpoints.

See `docs/data-plane-auth.md` for details.

## Deployment model

### Production

- Control-plane + event-processor: ECS Fargate or EKS
- Kafka: MSK
- Postgres: RDS / Aurora
- Redis: ElastiCache
- Data-plane: customer Kubernetes cluster

### Development

- Local docker-compose for control-plane, Kafka, Postgres, Redis
- Local Kubernetes for data-plane tests (optional)
- UI runs via `npm start`

## Design goals

- **Isolation:** tenant boundaries are enforced in control-plane and data-plane.
- **Simplicity:** data-plane only needs HTTPS egress to control-plane.
- **Auditability:** event stream is the source of truth for job history.
- **Scalability:** Kafka + Postgres allow horizontal processing growth.

## Related docs

- `docs/data-plane-auth.md`
- `docs/training-job-contract.md`
- `docs/contracts/contracts.md`
