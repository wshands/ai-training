"""Kafka consumer that persists job events and fans them out over Redis."""

# -----------------------
# Logging
# -----------------------

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
    """Configure process-wide logging with an env-driven log level."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True
    )


setup_logging()
logger = logging.getLogger(__name__)


import asyncio
import json
import logging
import os
import random
import uuid
from datetime import datetime
from pydantic import ValidationError
from typing import Any, Dict, Literal, Mapping, Optional, Tuple

import asyncpg
from asyncpg.exceptions import UniqueViolationError
import redis.asyncio as redis
from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import (
    GroupCoordinatorNotAvailableError,
    KafkaConnectionError,
    NoBrokersAvailable,
    TopicAlreadyExistsError,
    TopicAuthorizationFailedError,
    UnknownTopicOrPartitionError,
)

from common.ai_training_common.db import init_db
from common.ai_training_common.state_machine import JobState, apply_event
from common.ai_training_common.events import JobEventIn, JobEventOut
from common.ai_training_common.kafka import build_kafka_config
from common.ai_training_common.config import (
    JOB_MAX_RETRIES,
    JOB_RETRY_BASE_SECONDS,
    JOB_RETRY_MAX_SECONDS,
)


# -----------------------
# Config
# -----------------------

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
IN_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
POSTGRES_DSN = os.environ.get(
    "POSTGRES_DSN",
    "postgresql://postgres:postgres@postgres:5432/controlplane",
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
EVENT_RETENTION_DAYS = int(os.environ.get("EVENT_RETENTION_DAYS", "30"))
EVENT_PRUNE_INTERVAL_SECONDS = int(os.environ.get("EVENT_PRUNE_INTERVAL_SECONDS", "3600"))
KAFKA_AUTO_CREATE_TOPICS = os.environ.get("KAFKA_AUTO_CREATE_TOPICS", "true").lower() in ("1", "true", "yes")
KAFKA_TOPIC_PARTITIONS = int(os.environ.get("KAFKA_TOPIC_PARTITIONS", "3"))
KAFKA_TOPIC_REPLICATION_FACTOR = int(os.environ.get("KAFKA_TOPIC_REPLICATION_FACTOR", "2"))

MissingJobRowPolicy = Literal["warn", "raise", "upsert_stub"]

# -----------------------
# Utilities
# -----------------------

def _ts_to_pg_seconds(ts: Optional[int | float]) -> Optional[float]:
    """Normalize timestamps (ms or s) to seconds for PostgreSQL."""
    if ts is None:
        return None
    ts_f = float(ts)
    return ts_f / 1000.0 if ts_f >= 1_000_000_000_000 else ts_f


def _compute_retry_delay_seconds(retry_count: int) -> int:
    delay = JOB_RETRY_BASE_SECONDS * (2 ** max(retry_count, 0))
    return int(min(delay, JOB_RETRY_MAX_SECONDS))

async def wait_for_postgres(conn: asyncpg.Connection, timeout_s: int = 60) -> None:
    """Wait until the database responds to simple queries."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        try:
            await conn.execute("SELECT 1;")
            return
        except Exception:
            if asyncio.get_event_loop().time() > deadline:
                raise
            await asyncio.sleep(1)

async def wait_for_schema(conn: asyncpg.Connection, timeout_s: int = 60) -> None:
    """Wait for required tables to be present before consuming events."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    needed = {"jobs", "job_events", "job_state"}

    while True:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name = ANY($1::text[])
            """,
            list(needed),
        )
        have = {r["table_name"] for r in rows}
        if needed.issubset(have):
            return

        if asyncio.get_event_loop().time() > deadline:
            raise RuntimeError(f"DB schema not ready; have={have}")

        await asyncio.sleep(1)


async def apply_job_event_to_jobs_table(
    conn,
    *,
    job_id: str,
    tenant_id: str,
    user_id: str,
    ev_type: str,
    ts: Optional[int],
    config: Optional[Mapping[str, Any]] = None,
    on_missing_job_row: MissingJobRowPolicy = "warn",
) -> None:
    """
    Maintain job *metadata* in the `jobs` table.

    Source of truth for status is `job_state.last_state`.
    `jobs` is for:
      - config
      - submitted_at
      - updated_at
      - created_at (default)

    Missing-row policy for non-submit events:
      - warn (default)
      - raise
      - upsert_stub

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
    ts_sec = _ts_to_pg_seconds(ts)
    config_json = json.dumps(config) if config is not None else None

    if ev_type == "JOB_SUBMITTED":
        await conn.execute(
            """
            INSERT INTO jobs (job_id, tenant_id, user_id, config, submitted_at, updated_at)
            VALUES (
                $1,
                $2,
                $3,
                COALESCE($4::jsonb, '{}'::jsonb),
                COALESCE(to_timestamp($5), now()),
                COALESCE(to_timestamp($5), now())
            )
            ON CONFLICT (job_id) DO UPDATE
              SET tenant_id   = EXCLUDED.tenant_id,
                  user_id     = EXCLUDED.user_id,
                  submitted_at = COALESCE(jobs.submitted_at, EXCLUDED.submitted_at),
                  updated_at   = EXCLUDED.updated_at,
                  config       = CASE
                                  WHEN jobs.config = '{}'::jsonb
                                       AND EXCLUDED.config <> '{}'::jsonb
                                  THEN EXCLUDED.config
                                  ELSE jobs.config
                                END
            """,
            job_id,
            tenant_id,
            user_id,
            config_json,
            ts_sec,
        )
        return

    # ✅ Non-submit events: update existing row only; return an integer count
    updated = await conn.fetchval(
        """
        WITH u AS (
          UPDATE jobs
             SET updated_at = COALESCE(to_timestamp($2), now()),
                 config     = COALESCE($3::jsonb, jobs.config)
           WHERE job_id = $1
             AND tenant_id = $4
           RETURNING 1
        )
        SELECT count(*) FROM u;
        """,
        job_id,
        ts_sec,
        config_json,
        tenant_id,
    )

    if updated and int(updated) > 0:
        return

    # Missing jobs row for a non-submit event
    if on_missing_job_row == "warn":
        logger.warning(
            "apply_job_event_to_jobs_table: missing jobs row for job_id=%s ev_type=%s; ignored",
            job_id,
            ev_type,
        )
        return

    if on_missing_job_row == "raise":
        raise RuntimeError(
            f"Missing jobs row for job_id={job_id} while processing ev_type={ev_type}"
        )

    if on_missing_job_row == "upsert_stub":
        await conn.execute(
            """
            INSERT INTO jobs (job_id, tenant_id, user_id, config, submitted_at, updated_at)
            VALUES (
                $1,
                $2,
                $3,
                COALESCE($4::jsonb, '{}'::jsonb),
                NULL,
                COALESCE(to_timestamp($5), now())
            )
            ON CONFLICT (job_id) DO UPDATE
              SET tenant_id = EXCLUDED.tenant_id,
                  user_id = EXCLUDED.user_id,
                  updated_at = EXCLUDED.updated_at,
                  config     = CASE
                                WHEN jobs.config = '{}'::jsonb
                                     AND EXCLUDED.config <> '{}'::jsonb
                                THEN EXCLUDED.config
                                ELSE jobs.config
                              END
            """,
            job_id,
            tenant_id,
            user_id,
            config_json,
            ts_sec,
        )
        return

    raise ValueError(f"Unknown on_missing_job_row policy: {on_missing_job_row}")


async def process_event(conn: asyncpg.Connection, ev: JobEventIn) -> Optional[JobEventOut]:
    """
    Persist the event (idempotent on event_id), update job_state/jobs, and return
    a canonical object for Redis/WebSocket fan-out. Returns None if duplicate.
    """
    job_id = ev.job_id
    tenant_id = ev.tenant_id
    user_id = ev.user_id
    event_type = ev.event_type.value
    event_id = ev.event_id
    seq = ev.seq
    producer = ev.producer
    schema_version = ev.schema_version
    ts_ms = ev.ts_ms
    ts_sec = _ts_to_pg_seconds(ts_ms)

    details = ev.payload  # DETAILS ONLY

    async with conn.transaction():
        try:
            inserted = await conn.fetchrow(
                """
                INSERT INTO job_events(event_id, job_id, tenant_id, user_id, seq, event_type, producer, schema_version, event_time, payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, COALESCE(to_timestamp($9), now()), $10::jsonb)
                ON CONFLICT (event_id) DO NOTHING
                RETURNING id, job_id, tenant_id, user_id, event_time
                """,
                event_id,
                job_id,
                tenant_id,
                user_id,
                seq,
                event_type,
                producer,
                schema_version,
                ts_sec,
                json.dumps(details),
            )
        except UniqueViolationError:
            return None
        if inserted is None:
            return None

        db_id = int(inserted["id"])
        event_time = inserted["event_time"]

        row = await conn.fetchrow(
            "SELECT last_state FROM job_state WHERE job_id = $1 AND tenant_id = $2",
            job_id,
            tenant_id,
        )
        current_state = JobState(row["last_state"]) if row and row["last_state"] else None
        new_state = apply_event(current_state, event_type)

        # Retry scheduling: failed jobs can be re-queued with backoff.
        if event_type == "JOB_FAILED":
            job_row = await conn.fetchrow(
                """
                SELECT retry_count, max_retries
                FROM jobs
                WHERE job_id = $1 AND tenant_id = $2
                """,
                job_id,
                tenant_id,
            )
            if job_row:
                retry_count = int(job_row["retry_count"] or 0)
                max_retries_raw = job_row["max_retries"]
                max_retries = JOB_MAX_RETRIES if max_retries_raw is None else int(max_retries_raw)
                if retry_count < max_retries:
                    delay_seconds = _compute_retry_delay_seconds(retry_count)
                    await conn.execute(
                        """
                        UPDATE jobs
                        SET retry_count = $1,
                            max_retries = $2,
                            next_run_at = now() + ($3::int || ' seconds')::interval,
                            locked_by = NULL,
                            locked_at = NULL,
                            updated_at = now()
                        WHERE job_id = $4 AND tenant_id = $5
                        """,
                        retry_count + 1,
                        max_retries,
                        delay_seconds,
                        job_id,
                        tenant_id,
                    )
                    logger.info(
                        "Scheduled retry for job_id=%s in %ss (attempt %s/%s)",
                        job_id,
                        delay_seconds,
                        retry_count + 1,
                        max_retries,
                    )
                    new_state = JobState.RETRYING
                else:
                    await conn.execute(
                        """
                        UPDATE jobs
                        SET locked_by = NULL,
                            locked_at = NULL,
                            updated_at = now()
                        WHERE job_id = $1 AND tenant_id = $2
                        """,
                        job_id,
                        tenant_id,
                    )

        if event_type in ("JOB_COMPLETED", "JOB_CANCELLED"):
            await conn.execute(
                """
                UPDATE jobs
                SET locked_by = NULL,
                    locked_at = NULL,
                    next_run_at = NULL,
                    updated_at = now()
                WHERE job_id = $1 AND tenant_id = $2
                """,
                job_id,
                tenant_id,
            )

        # Store details only in last_event (recommended; keeps job_state small and consistent)
        await conn.execute(
            """
            INSERT INTO job_state(job_id, tenant_id, user_id, last_state, last_event, last_event_id, last_seq, updated_at)
            VALUES($1, $2, $3, $4, $5::jsonb, $6, $7, now())
            ON CONFLICT(job_id) DO UPDATE
              SET tenant_id = EXCLUDED.tenant_id,
                  user_id = EXCLUDED.user_id,
                  last_state = EXCLUDED.last_state,
                  last_event = EXCLUDED.last_event,
                  last_event_id = EXCLUDED.last_event_id,
                  last_seq = EXCLUDED.last_seq,
                  updated_at = now()
            """,
            job_id,
            tenant_id,
            user_id,
            new_state.value,
            json.dumps(details),
            event_id,
            seq,
        )

        cfg = details.get("config") if event_type == "JOB_SUBMITTED" else None
        await apply_job_event_to_jobs_table(
            conn,
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=user_id,
            ev_type=event_type,
            ts=ts_ms,
            config=cfg,
            on_missing_job_row="warn",
        )

        return JobEventOut(
            id=db_id,
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=user_id,
            event_time=event_time.isoformat() if isinstance(event_time, datetime) else str(event_time),
            event_type=event_type,
            seq=int(seq or 0),
            ts_ms=int(ts_ms or 0),
            producer=str(producer or "unknown"),
            schema_version=int(schema_version or 1),
            data=details or {},
            state=new_state.value,
        )



# Retry logic for starting Kafka consumer
# Make the consumer resilient anyway (retry start, and handle transient errors
async def start_consumer_with_retry(consumer, kafka_config: Dict[str, Any], tries: int = 60) -> None:
    """Start a Kafka consumer with retry/backoff for transient errors."""
    delay = 0.5
    create_attempted = False
    for i in range(tries):
        try:
            await consumer.start()
            return
        except (
            GroupCoordinatorNotAvailableError,
            KafkaConnectionError,
            NoBrokersAvailable,
        ) as e:
            # jitter avoids thundering herd when multiple services start together
            jitter = random.uniform(0, 0.25)
            print(f"Kafka not ready ({type(e).__name__}): retrying in {delay:.2f}s", flush=True)
            await asyncio.sleep(delay + jitter)
            delay = min(delay * 1.3, 5.0)
        except UnknownTopicOrPartitionError:
            if KAFKA_AUTO_CREATE_TOPICS and not create_attempted:
                create_attempted = True
                if await ensure_topic(kafka_config):
                    continue
            jitter = random.uniform(0, 0.25)
            print("Kafka topic missing: retrying after create attempt", flush=True)
            await asyncio.sleep(delay + jitter)
            delay = min(delay * 1.3, 5.0)
    raise RuntimeError("Kafka never became ready (topic/coordinator) after retries")


async def ensure_topic(kafka_config: Dict[str, Any]) -> bool:
    """Ensure the Kafka topic exists; returns True if it exists/created."""
    admin = AIOKafkaAdminClient(**kafka_config)
    try:
        await admin.start()
        topic = NewTopic(
            name=IN_TOPIC,
            num_partitions=KAFKA_TOPIC_PARTITIONS,
            replication_factor=KAFKA_TOPIC_REPLICATION_FACTOR,
        )
        await admin.create_topics([topic])
        logger.info("Created Kafka topic %s", IN_TOPIC)
        return True
    except TopicAlreadyExistsError:
        return True
    except TopicAuthorizationFailedError:
        logger.error("Not authorized to create Kafka topic %s", IN_TOPIC)
        return False
    except Exception:
        logger.exception("Failed to create Kafka topic %s", IN_TOPIC)
        return False
    finally:
        await admin.close()


async def publish_ws_event(r: redis.Redis, out: JobEventOut) -> None:
    """Publish a processed event to the tenant Redis channel."""
    channel = f"job_events:{out.tenant_id}"
    await r.publish(channel, out.model_dump_json())


async def prune_old_events_loop(dsn: str) -> None:
    """Periodically prune old job events based on retention settings."""
    if EVENT_RETENTION_DAYS <= 0:
        logger.info("Event retention disabled; skipping prune loop")
        return

    conn = await asyncpg.connect(dsn)
    try:
        while True:
            try:
                result = await conn.execute(
                    """
                    DELETE FROM job_events
                    WHERE event_time < now() - ($1::text || ' days')::interval
                    """,
                    str(EVENT_RETENTION_DAYS),
                )
                logger.info("Pruned old job_events: %s", result)
            except Exception:
                logger.exception("Failed to prune old job_events")
            await asyncio.sleep(EVENT_PRUNE_INTERVAL_SECONDS)
    finally:
        await conn.close()


async def main() -> None:
    """Run the event processor loop (consume, persist, fan out)."""
    await init_db()
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    conn = await asyncpg.connect(POSTGRES_DSN)
    await wait_for_postgres(conn, timeout_s=60)
    await wait_for_schema(conn, timeout_s=60)
    asyncio.create_task(prune_old_events_loop(POSTGRES_DSN))

    kafka_config = build_kafka_config()
    if KAFKA_AUTO_CREATE_TOPICS:
        await ensure_topic(kafka_config)
    consumer = AIOKafkaConsumer(
        IN_TOPIC,
        group_id="event-processor",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,
        max_poll_interval_ms=15 * 60 * 1000,
        max_poll_records=10,
        **kafka_config,
    )

    await start_consumer_with_retry(consumer, kafka_config)
    try:
        async for msg in consumer:
            try:
                ev = JobEventIn.model_validate(msg.value)
            except ValidationError as e:
                logger.warning("Dropping invalid event: %s value=%r", e, msg.value)
                await consumer.commit()
                continue

            if not ev.job_id:
                await consumer.commit()
                continue

            ws_event = await process_event(conn, ev)
            if ws_event is not None:
                await publish_ws_event(r, ws_event)

            try:
                await consumer.commit()
            except Exception as e:
                logger.warning("Commit failed (rebalance?): %s", e)
    finally:
        await consumer.stop()
        await r.aclose()
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
