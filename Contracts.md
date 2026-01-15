# Contracts (Locked Before Implementation)

This document defines the **hard contracts** between components in this repo:
- **Producers/Consumers** via Kafka `job-events`
- **Persistence** via Postgres (`jobs`, `job_state`, `job_events`)
- **API surface** for UI + tooling
- **Kubernetes job runner** interface (ConfigMap/Secret/env/logs/metrics)

If a change breaks this document, bump **schema_version** (events) and/or **api_version** (HTTP), and maintain backward compatibility per the rules below.

---

## 1) Kafka Event Contract (`job-events` topic)

### 1.1 Envelope (required for all events) — **v1**
All events MUST conform to this envelope:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "type": "JOB_SUBMITTED | JOB_STARTED | JOB_LOG | EPOCH_METRIC | JOB_COMPLETED | JOB_FAILED | ...",
  "job_id": "uuid",
  "seq": 1,
  "ts_ms": 1700000000000,
  "producer": "control-plane | job-launcher | training-job | event-processor",
  "payload": { }
}
```

#### Field semantics
- `schema_version` (int): bump when changing semantics or required fields.
- `event_id` (uuid string): **global idempotency key**.
- `type` (string): event type enum.
- `job_id` (uuid string): job correlation id.
- `seq` (int): **monotonic per-job** sequence number (starts at 1).
- `ts_ms` (int): event time in epoch **milliseconds**.
- `producer` (string): emitting service identity.
- `payload` (object): event-type specific data (see below).

#### Ordering + partitions
- Kafka key MUST be `job_id` to ensure **per-job ordering** within a partition.
- Consumers MUST NOT assume global ordering across jobs.

#### Compatibility rules
- Consumers MUST ignore unknown `payload` fields.
- Producers MUST NOT remove or change meaning of required envelope fields within a schema_version.
- When bumping `schema_version`, consumers should support **at least the previous version** during rollout.

### 1.2 Event types (payload schemas)

#### `JOB_SUBMITTED`
```json
"payload": {
  "config": {
    "model_id": "string",
    "dataset_id": "string",
    "epochs": 1,
    "batch_size": 32,
    "lr": 0.001,
    "distributed": false,
    "extra": {}
  }
}
```

#### `JOB_STARTED`
```json
"payload": {
  "runner": "training-job",
  "image": "string",
  "node": "string|null",
  "pod": "string|null"
}
```

#### `JOB_LOG`
```json
"payload": {
  "level": "DEBUG|INFO|WARNING|ERROR",
  "message": "string"
}
```

#### `EPOCH_METRIC`
```json
"payload": {
  "epoch": 1,
  "metrics": {
    "loss": 0.123,
    "accuracy": 0.98
  }
}
```

#### `JOB_COMPLETED`
```json
"payload": {
  "result": { }
}
```

#### `JOB_FAILED`
```json
"payload": {
  "error": {
    "message": "string",
    "type": "string|null",
    "stack": "string|null"
  }
}
```

---

## 2) Postgres Contract

### 2.1 Tables

#### `jobs` — immutable-ish job configuration + timestamps
Required columns:
- `job_id TEXT PRIMARY KEY`
- `created_at TIMESTAMP NOT NULL DEFAULT now()`
- `submitted_at TIMESTAMP`
- `updated_at TIMESTAMP`
- `config JSONB NOT NULL`

Rules:
- `config` written on `JOB_SUBMITTED` and never mutated except by explicit migration rules.
- `updated_at` set when any job event is processed (optional but recommended).

#### `job_events` — append-only event log (source of truth)
Required columns:
- `id BIGSERIAL PRIMARY KEY`
- `event_id TEXT NOT NULL`
- `job_id TEXT NOT NULL`
- `seq BIGINT NOT NULL`
- `event_type TEXT NOT NULL`
- `producer TEXT NOT NULL`
- `schema_version INT NOT NULL`
- `event_time TIMESTAMP NOT NULL`
- `payload JSONB NOT NULL`

Constraints (idempotency + correctness):
- `UNIQUE(event_id)`
- `UNIQUE(job_id, seq)`
- Indexes:
  - `(job_id, seq)`
  - `(job_id, id)`
  - `(event_type)`
  - `(event_time DESC)`

#### `job_state` — derived current state (denormalized)
Required columns:
- `job_id TEXT PRIMARY KEY`
- `last_state TEXT NOT NULL`
- `last_event_id TEXT NOT NULL`
- `last_seq BIGINT NOT NULL`
- `updated_at TIMESTAMP NOT NULL DEFAULT now()`
- `last_event JSONB NOT NULL DEFAULT '{}'::jsonb` (optional but useful)

Rules:
- `job_state` MUST be updated **only** by the event processor, from events in `job_events`.
- `last_state` MUST be computed by the FSM (see §2.2) and must be consistent with `last_seq`.

### 2.2 State machine rules
- `job_state.last_state` is the **source of truth** for current status.
- `jobs` list endpoints read status from `job_state.last_state`.
- Replaying the event log MUST produce the same state as `job_state`.

---

## 3) HTTP API Contract (Control Plane)

### 3.1 Common response + error model

Success response envelope:
```json
{ "data": <payload> }
```

Error response envelope:
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "details": {},
    "trace_id": "string|null"
  }
}
```

### 3.2 Endpoints

#### `POST /jobs/train`
Request:
```json
{
  "model_id": "string",
  "dataset_id": "string",
  "epochs": 1,
  "batch_size": 32,
  "lr": 0.001,
  "distributed": false,
  "extra": {}
}
```

Response:
```json
{ "data": { "job_id": "uuid" } }
```

Behavior:
- Persists initial `jobs` row (or does so via event processor).
- Emits `JOB_SUBMITTED` event (v1 envelope).

#### `GET /jobs`
Query params:
- `limit` (1..200, default 50)
- `cursor` (opaque string; optional)
- `status` (repeatable; optional)
- `created_after_ms` / `created_before_ms` (optional)
- `model_id` / `dataset_id` (optional)

Response:
```json
{
  "data": {
    "items": [ <JobSummary> ],
    "next_cursor": "string|null"
  }
}
```

`JobSummary`:
```json
{
  "job_id": "uuid",
  "status": "SUBMITTED|PENDING|RUNNING|SUCCEEDED|FAILED",
  "created_at": "iso8601",
  "submitted_at": "iso8601|null",
  "updated_at": "iso8601|null",
  "model_id": "string|null",
  "dataset_id": "string|null"
}
```

#### `GET /jobs/{job_id}`
Response:
```json
{ "data": <JobDetail> }
```

`JobDetail`:
- Includes `JobSummary` fields + `config` + optional derived fields.
- MUST read status from `job_state` (not ad hoc replay logic).

#### `GET /jobs/{job_id}/events`
Query params:
- `since_id` OR `since_seq` (optional)
- `limit` (1..500, default 200)

Response:
```json
{
  "data": {
    "items": [ <Event> ],
    "next_since_id": 123
  }
}
```

#### `GET /ws/jobs/{job_id}`
WebSocket:
- Client may send:
  ```json
  { "type": "RESUME", "since_id": 123 }
  ```
- Server sends:
  - `"HISTORY"` frames (optional, bounded)
  - `"EVENT"` frames for live stream
  - Heartbeats

---

## 4) Kubernetes Job Contract

### 4.1 Inputs to training container

#### ConfigMap
Name: `train-<jobid8>-config`

Required key:
- `config.json` — JSON with the same `payload.config` structure as `JOB_SUBMITTED`.

#### Secrets (optional but standardized)
If secrets are needed, mount a Secret with:
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (optional)
- `HF_TOKEN` (optional)
- `DATASET_CREDENTIALS_JSON` (optional)

### 4.2 Environment variables
Training container MUST receive:
- `KAFKA_BOOTSTRAP`
- `KAFKA_TOPIC`  (**not** `JOB_EVENTS_TOPIC`)
- `JOB_CONFIG=/opt/job/config.json`
- `JOB_ID=<job_id>`

### 4.3 Logs + metrics
- The training container MUST emit Kafka events for:
  - Logs: `JOB_LOG` with `{level,message}`
  - Metrics: `EPOCH_METRIC` with `{epoch,metrics}`
- (Optional) stdout logs should be JSON lines:
  ```json
  {"ts_ms":..., "level":"INFO", "job_id":"...", "msg":"..."}
  ```

---

## 5) Operational Guarantees

### 5.1 Delivery + idempotency
- Assume Kafka delivers **at least once**.
- Therefore:
  - Producers MUST set `event_id`.
  - DB MUST dedupe on `event_id` and/or `(job_id, seq)`.
  - Event processor MUST be safe to re-run events.

### 5.2 Observability
- Every HTTP error includes `trace_id` (or request id).
- Every event includes `producer` and `schema_version`.

---
