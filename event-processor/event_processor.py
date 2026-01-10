import logging
import os
# Why put logging setup outside main()?
# Anything imported before you call setup_logging() might emit logs (or configure logging itself).
# Calling it at module import time ensures all logs (including early startup) use your format/level.
# In containers, the entrypoint module is the natural “one-time per process” place.
# force=True tells Python to remove any existing logging handlers and reconfigure
# logging with your settings. This is useful in container apps because frameworks
# (uvicorn/gunicorn) or imported libraries might configure logging before your code runs.
def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True
    )


setup_logging()
logger = logging.getLogger(__name__)



import asyncio
import asyncpg
import json
import os
import random
import redis.asyncio as redis

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import (
    UnknownTopicOrPartitionError,
    GroupCoordinatorNotAvailableError,
    KafkaConnectionError,
    NoBrokersAvailable,
)
from datetime import datetime
from state_machine import apply_event, JobState
from typing import Any, Mapping, Optional, Literal


KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
IN_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/controlplane")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")  # or wherever your Redis lives


async def wait_for_postgres(conn, timeout_s: int = 60):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        try:
            await conn.execute("SELECT 1;")
            return
        except Exception:
            if asyncio.get_event_loop().time() > deadline:
                raise
            await asyncio.sleep(1)

async def wait_for_schema(conn, timeout_s: int = 60):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name IN ('jobs', 'job_events', 'job_state')
            """
        )
        have = {r["table_name"] for r in rows}
        if {"jobs", "job_events", "job_state"}.issubset(have):
            return

        if asyncio.get_event_loop().time() > deadline:
            raise RuntimeError(f"DB schema not ready; have={have}")

        await asyncio.sleep(1)




MissingJobRowPolicy = Literal["warn", "raise", "upsert_stub"]


def _rows_affected(status: str) -> int:
    """
    Parse asyncpg status strings like:
      - "UPDATE 0"
      - "UPDATE 1"
      - "INSERT 0 1"
    and return the affected row count (best-effort).
    """
    parts = status.split()
    if not parts:
        return 0

    # Typical cases:
    # UPDATE <n>
    if parts[0].upper() == "UPDATE" and len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])

    # INSERT <oid> <n>
    if parts[0].upper() == "INSERT" and len(parts) >= 3 and parts[2].isdigit():
        return int(parts[2])

    # Fallback: try last token
    if parts[-1].isdigit():
        return int(parts[-1])

    return 0


async def apply_job_event_to_jobs_table(
    conn,
    *, # Everything after * must be passed by keyword, not position.
    job_id: str,
    ev_type: str,
    # The quotes mean forward reference: Python will treat "JobState" 
    # as a type name even if JobState is defined later (or only
    #  available at type-check time).
    # In practice it might be an Enum where you store new_state.value into the DB.
    new_state: "JobState",  # or Enum/str; align with your codebase
    ts: Optional[int],
    config: Optional[Mapping[str, Any]] = None,
    on_missing_job_row: MissingJobRowPolicy = "warn",
) -> None:
    """
    Persist a job's current status (and initial metadata) into the `jobs` table.

    Why `JOB_SUBMITTED` is handled differently
    -----------------------------------------
    `JOB_SUBMITTED` is the canonical "create job" event. We UPSERT because:

    - The `jobs` row may not exist yet, so we must `INSERT`.
    - The event stream is typically at-least-once (retries/duplicates happen), so we must be
      idempotent: `INSERT ... ON CONFLICT DO UPDATE` is safe under reprocessing.
    - Creation-time fields should be preserved under replay:
        * `submitted_at` uses first non-null wins (don't overwrite the original submit time).
        * `config` prefers the existing value and only fills from submission if missing.

    All other events mutate an existing job row (status + updated_at only), and intentionally
    do NOT create rows to avoid “phantom jobs” from stray/out-of-context events.

    Out-of-order events and missing-row handling
    --------------------------------------------
    In distributed systems it can happen that a non-submit event is observed before `JOB_SUBMITTED`.
    In this design, the UPDATE would affect 0 rows. We detect that and apply a policy:

    - "warn" (default): log a warning (recommended during development/early production).
    - "raise": raise an exception to surface ordering/producer bugs quickly.
    - "upsert_stub": create a minimal placeholder row so later reads see something, but with
      weaker semantics (use only if you *want* resilience over strictness).

    Parameters
    ----------
    on_missing_job_row:
        What to do when a non-submit event updates 0 rows.

    Returns
    -------
    None
    """
    config_json = json.dumps(config) if config is not None else None

    if ev_type == "JOB_SUBMITTED":
        await conn.execute(
            """
            INSERT INTO jobs (job_id, config, status, submitted_at, updated_at)
            VALUES (
                $1,
                COALESCE($2::jsonb, '{}'::jsonb),
                $3,
                COALESCE(to_timestamp($4), now()),
                COALESCE(to_timestamp($4), now())
            )
            ON CONFLICT (job_id) DO UPDATE
              SET status       = EXCLUDED.status,
                  submitted_at = COALESCE(jobs.submitted_at, EXCLUDED.submitted_at),
                  updated_at   = EXCLUDED.updated_at,
                  config       = COALESCE(jobs.config, EXCLUDED.config)
            """,
            job_id,
            config_json,
            new_state.value,
            ts,
        )
        return

    # Non-submit event: update existing job row
    status = await conn.execute(
        """
        UPDATE jobs
           SET status     = $2,
               updated_at = COALESCE(to_timestamp($3), now())
         WHERE job_id     = $1
        """,
        job_id,
        new_state.value,
        ts,
    )

    if _rows_affected(status) > 0:
        return

    # UPDATE hit 0 rows -> missing job row (out-of-order or missing submit)
    msg = (
        f"jobs row missing for job_id={job_id!r} while processing ev_type={ev_type!r}. "
        f"Likely out-of-order events or missing JOB_SUBMITTED."
    )

    if on_missing_job_row == "warn":
        logger.warning(msg)
        return

    if on_missing_job_row == "raise":
        raise RuntimeError(msg)

    if on_missing_job_row == "upsert_stub":
        # Create a minimal row (stub) so the job exists. Note: semantics are weaker because we
        # didn't see the true submit/config yet.
        await conn.execute(
            """
            INSERT INTO jobs (job_id, config, status, submitted_at, updated_at)
            VALUES (
                $1,
                '{}'::jsonb,
                $2,
                NULL,
                COALESCE(to_timestamp($3), now())
            )
            ON CONFLICT (job_id) DO UPDATE
              SET status     = EXCLUDED.status,
                  updated_at = EXCLUDED.updated_at
            """,
            job_id,
            new_state.value,
            ts,
        )
        logger.warning("%s (created stub row via on_missing_job_row='upsert_stub')", msg)
        return

    # Defensive: if someone passes an unexpected policy
    raise ValueError(f"Unknown on_missing_job_row policy: {on_missing_job_row!r}")


def _normalize_event_type(ev: dict) -> str:
    return ev.get("event_type") or ev.get("type") or "UNKNOWN"


async def process_event(conn, ev) -> dict:
    """
    Persists the event, updates job_state/jobs, and returns a canonical
    envelope suitable for Redis/WebSocket fan-out.
    """
    ws_event: dict | None = None

    async with conn.transaction():
        # 1) Insert job_event + capture id/time for ordering
        inserted = await conn.fetchrow(
            """
            INSERT INTO job_events(job_id, event_time, payload)
            VALUES ($1, COALESCE(to_timestamp($2), now()), $3::jsonb)
            RETURNING id, job_id, event_time
            """,
            ev["job_id"],
            ev.get("timestamp"),
            json.dumps(ev),
        )

        event_id = inserted["id"]
        job_id = inserted["job_id"]
        event_time = inserted["event_time"]

        # 2) Load current state
        row = await conn.fetchrow(
            "SELECT last_state FROM job_state WHERE job_id = $1",
            job_id,
        )
        current_state = JobState(row["last_state"]) if row and row["last_state"] else None

        # 3) Apply FSM transition using normalized event type
        event_type = _normalize_event_type(ev)
        new_state = apply_event(current_state, event_type)

        # 4) Upsert job_state
        await conn.execute(
            """
            INSERT INTO job_state(job_id, last_state, last_event, updated_at)
            VALUES($1, $2, $3::jsonb, now())
            ON CONFLICT(job_id) DO UPDATE
              SET last_state = EXCLUDED.last_state,
                  last_event = EXCLUDED.last_event,
                  updated_at = now()
            """,
            job_id,
            new_state.value,
            json.dumps(ev),
        )

        # 5) Update jobs table if applicable
        #await upsert_job_row(conn, ev, new_state)
        await apply_job_event_to_jobs_table(conn, 
            job_id=job_id,
            ev_type=event_type,
            new_state=new_state,
            ts=ev.get("timestamp"),
            config=ev.get("config"),
            on_missing_job_row="warn",
        )

        # Build canonical envelope (publish AFTER commit, outside txn)
        ws_event = {
            "id": int(event_id),
            "job_id": job_id,
            "event_time": event_time.isoformat() if isinstance(event_time, datetime) else str(event_time),
            "event_type": event_type,
            "payload": ev,             # original event dict (contains message/loss/etc.)
            "state": new_state.value,  # handy for UI status updates
        }

    # Return after commit
    return ws_event  # type: ignore



# Retry logic for starting Kafka consumer
# Make the consumer resilient anyway (retry start, and handle transient errors
async def start_consumer_with_retry(consumer, tries: int = 60) -> None:
    delay = 0.5
    for i in range(tries):
        try:
            await consumer.start()
            return
        except (
            UnknownTopicOrPartitionError,
            GroupCoordinatorNotAvailableError,
            KafkaConnectionError,
            NoBrokersAvailable,
        ) as e:
            # jitter avoids thundering herd when multiple services start together
            jitter = random.uniform(0, 0.25)
            print(f"Kafka not ready ({type(e).__name__}): retrying in {delay:.2f}s", flush=True)
            await asyncio.sleep(delay + jitter)
            delay = min(delay * 1.3, 5.0)
    raise RuntimeError("Kafka never became ready (topic/coordinator) after retries")


async def main():
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    conn = await asyncpg.connect(POSTGRES_DSN)
    await wait_for_postgres(conn, timeout_s=60)
    await wait_for_schema(conn, timeout_s=60)

    consumer = AIOKafkaConsumer(
        IN_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="event-processor",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,   # <- recommended
    )

    await start_consumer_with_retry(consumer)  # <- key change
    try:
        async for msg in consumer:
            ev = msg.value
            if not ev or "job_id" not in ev:
                await consumer.commit()
                continue

            ws_event = await process_event(conn, ev)
            channel = f"job_events:{ws_event['job_id']}"
            # publish the raw event payload (the thing that actually has "type", "message", "loss", etc.)
            payload = ws_event["payload"]
            payload["_id"] = ws_event["id"]
            payload["_state"] = ws_event["state"]
            await r.publish(channel, json.dumps(payload))

            await consumer.commit()  # <- commit only after DB + redis
    finally:
        await consumer.stop()
        await r.aclose()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
