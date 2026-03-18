# Architecture Patterns in AITrainOps

This document captures the main software and distributed-systems patterns used
in the AITrainOps codebase, with concrete implementation pointers.

## 1) Event-Driven Architecture + Event Sourcing

Job lifecycle changes are represented as events and persisted in an append-only
event log (`job_events`). Read models (`job_state`) are derived from events.

Why it is used:
- Auditable lifecycle history
- Deterministic state projection
- Decoupled producers and consumers

Where:
- Event envelope: `common/ai_training_common/events.py`
- Event persistence and projection: `control-plane/event-processor/event_processor.py`
- Event storage tables: `common/ai_training_common/db.py`

## 2) Explicit State Machine (Finite State Machine)

State transitions are centralized in a transition table and applied uniformly by
the event-processor.

Why it is used:
- Prevent ad hoc state transitions
- Keep lifecycle rules easy to inspect and test

Where:
- `common/ai_training_common/state_machine.py`

## 3) Strategy Pattern for Event Bus Provider

Runtime provider selection (`EVENT_BUS_PROVIDER`) switches behavior between SQS
and Kafka without changing call sites.

Why it is used:
- Deployment flexibility (SQS default, Kafka optional)
- Keeps bus-specific logic isolated

Where:
- Producer-side strategy: `control-plane/api/app/event_bus.py`
- Consumer-side strategy: `control-plane/event-processor/event_processor.py`

## 4) Adapter / Facade over Infrastructure SDKs

`send_event(...)` provides a single app-facing contract while hiding SQS/Kafka
SDK details.

Why it is used:
- Simplifies API and domain code
- Reduces transport-coupled branching across the app

Where:
- `control-plane/api/app/event_bus.py`

## 5) Idempotent Consumer Pattern

Event processing is designed for at-least-once delivery and deduplicates with
`event_id`.

Why it is used:
- Safe reprocessing on retries/rebalances/redelivery
- Prevents duplicate side effects for the same lifecycle event

Where:
- `ON CONFLICT (event_id) DO NOTHING` in event insert:
  `control-plane/event-processor/event_processor.py`
- SQS FIFO dedupe key (`MessageDeduplicationId=event_id`):
  `control-plane/api/app/event_bus.py`

## 6) Repository / Data Access Layer

DB operations are centralized in `common/ai_training_common/db.py` as reusable
async functions (rather than scattered SQL in handlers).

Why it is used:
- Shared data access logic across services
- Better maintainability and testability

Where:
- `common/ai_training_common/db.py`

## 7) Competing Consumers + Lease-Based Work Claiming

Multiple launcher agents can poll concurrently. Claims use row locks and lease
fields (`locked_by`, `locked_at`) to avoid duplicate execution.

Why it is used:
- Horizontal scaling of job launchers
- Crash recovery via lock timeout

Where:
- Atomic claim query with `FOR UPDATE SKIP LOCKED`:
  `common/ai_training_common/db.py`
- Claim endpoint:
  `control-plane/api/app/main.py` (`POST /internal/jobs/claim`)

## 8) Retry with Exponential Backoff

On failure, retries are scheduled with bounded exponential delay and represented
as a new job attempt.

Why it is used:
- Better resilience for transient failures
- Preserves audit history of attempts

Where:
- Retry math and config transformation:
  `common/ai_training_common/retry.py`
- Retry scheduling and new job creation:
  `control-plane/event-processor/event_processor.py`

## 9) Dependency Injection for Auth and Authorization

FastAPI `Depends(...)` composes authN/authZ and billing checks at endpoint
boundaries.

Why it is used:
- Consistent security enforcement
- Keeps endpoint handlers focused on business behavior

Where:
- Role/billing dependencies and guards:
  `control-plane/api/app/main.py`

## 10) Pub/Sub Fan-Out for Real-Time UI

The event-processor publishes normalized events to Redis channels; WebSocket
handlers subscribe and forward to tenant clients.

Why it is used:
- Decouples processing from client streaming
- Supports multiple concurrent UI subscribers

Where:
- Redis publish:
  `control-plane/event-processor/event_processor.py`
- WebSocket subscription and forwarding:
  `control-plane/api/app/main.py`

## Notes on Pattern Composition

Patterns are intentionally combined:
- Event sourcing + FSM gives deterministic lifecycle progression.
- Idempotent consumer + FIFO ordering constraints gives robust delivery
  semantics under retries.
- Lease-based claiming complements event-driven status updates for data-plane
  execution control.
