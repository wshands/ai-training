# Job Queueing and Retries

This document describes the queue semantics used by the data-plane and how
retry scheduling works.

## Why queueing exists

The data-plane can run multiple launcher instances. If each launcher simply
polls for "SUBMITTED" jobs, the same job can be picked up more than once.

Queueing solves this by:

- Atomically claiming a job so only one agent executes it
- Tracking lock ownership and timeout for crash recovery
- Scheduling retries with backoff when jobs fail

## Claiming jobs

The data-plane uses:

```
POST /internal/jobs/claim
```

This endpoint:

1) Selects jobs in `SUBMITTED` or `RETRYING` state
2) Ensures `next_run_at <= now()` (ready to run)
3) Skips jobs locked by another agent unless the lock is expired
4) Updates the job row with `locked_by` and `locked_at`

Only the claiming agent receives the job in the response.

## Lock timeout

If a launcher crashes after claiming a job, another launcher can reclaim it
once the lock is older than `JOB_LOCK_TIMEOUT_SECONDS`.

This keeps the system moving without manual intervention.

## Retry scheduling

The event-processor schedules retries when it consumes a `JOB_FAILED` event.

Rules:

- If `retry_count < max_retries`, the job is rescheduled
- `next_run_at` is set using exponential backoff
- `job_state` is set to `RETRYING`
- The job becomes available to claim once `next_run_at` is reached

If retries are exhausted, the job remains `FAILED`.

## Schema fields

The `jobs` table includes:

- `retry_count`: current retry attempt
- `max_retries`: max attempts for this job
- `next_run_at`: time the job becomes claimable
- `locked_by`: agent id that claimed the job
- `locked_at`: time the job was claimed

## Config knobs

Environment variables:

- `JOB_MAX_RETRIES` (default 3)
- `JOB_RETRY_BASE_SECONDS` (default 30)
- `JOB_RETRY_MAX_SECONDS` (default 900)
- `JOB_LOCK_TIMEOUT_SECONDS` (default 300)

## Data-plane flow (summary)

1) Launcher calls `POST /internal/jobs/claim`.
2) For each claimed job, launcher emits `JOB_PENDING`.
3) Launcher creates a Kubernetes Job.
4) Training job emits `JOB_STARTED`, `JOB_COMPLETED`, `JOB_FAILED`, etc.
5) Event-processor updates state and schedules retries if needed.

