# Training Job Contract

This document defines the contract for customer-provided training job images.
It describes required inputs and how the training job reports logs/metrics.

## Inputs

### ConfigMap

The job-launcher mounts a ConfigMap at `/opt/job/config.json`.

- `JOB_CONFIG=/opt/job/config.json`
- The JSON contents match the `payload.config` in `JOB_SUBMITTED`.

Example (excerpt):

```json
{
  "job_id": "uuid",
  "tenant_id": "org_123",
  "user_id": "user_456",
  "model_id": "resnet50",
  "dataset_id": "imagenet",
  "epochs": 5,
  "batch_size": 32,
  "lr": 0.001,
  "distributed": false,
  "extra": {}
}
```

### Environment variables

Required:

- `JOB_ID=<job_id>`
- `JOB_CONFIG=/opt/job/config.json`
- `CONTROL_PLANE_URL=<https://control-plane-host>`
- `DATA_PLANE_API_TOKEN=<token>`
- `DATA_PLANE_TENANT_ID=<tenant_id>`

Optional (if you need AWS or external credentials):

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`
- `HF_TOKEN`
- `DATASET_CREDENTIALS_JSON`

## Event reporting

Training jobs send events to the control-plane:

```
POST /internal/events
Authorization: Bearer <DATA_PLANE_API_TOKEN>
X-Tenant-Id: <DATA_PLANE_TENANT_ID>
```

Required event types:

- `JOB_LOG` — log messages
- `EPOCH_METRIC` — per-epoch metrics
- `JOB_METRIC` — aggregate metrics (optional)
- `JOB_FAILED` — fatal errors
- `JOB_COMPLETED` — success

### Example event payload (JOB_LOG)

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "event_type": "JOB_LOG",
  "job_id": "uuid",
  "tenant_id": "org_123",
  "user_id": "user_456",
  "seq": 5,
  "ts_ms": 1700000000000,
  "producer": "training-job",
  "payload": {
    "level": "INFO",
    "message": "Epoch 1 started"
  }
}
```

## Tips

- `seq` must be monotonic per job.
- Use `event_id` for idempotency.
- If you batch logs/metrics, keep ordering by `seq`.
- Terminal events are mutually exclusive (e.g., `JOB_COMPLETED`, `JOB_FAILED`, `JOB_CANCELLED`). The runtime guards against emitting more than one terminal event per job.
