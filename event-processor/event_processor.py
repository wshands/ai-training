# import asyncio, os, json
# from aiokafka import AIOKafkaConsumer
# import asyncpg

import asyncio
import asyncpg
import json
import os
from aiokafka import AIOKafkaConsumer
import redis.asyncio as redis

from state_machine import apply_event, JobState

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
IN_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/controlplane")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")  # or wherever your Redis lives


async def ensure_db(conn):
    await conn.execute("""CREATE TABLE IF NOT EXISTS job_events (
        id BIGSERIAL PRIMARY KEY,
        job_id TEXT NOT NULL,
        event_time TIMESTAMP,
        payload JSONB
    );""")
    await conn.execute("""CREATE TABLE IF NOT EXISTS job_state (
        job_id TEXT PRIMARY KEY,
        last_state TEXT,
        last_event JSONB,
        updated_at TIMESTAMP
    );""")


async def upsert_job_row(conn, ev, new_state: JobState):
    job_id = ev["job_id"]
    ev_type = ev.get("type")
    ts = ev.get("timestamp")  # epoch seconds or None
    config = ev.get("config")  # only on JOB_SUBMITTED

    # Only lifecycle events should affect jobs.status
    if ev_type not in ("JOB_SUBMITTED", "JOB_STARTED", "JOB_COMPLETED", "JOB_FAILED", "JOB_PREEMPTED", "JOB_CANCELLED"):
        return

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
            json.dumps(config) if config is not None else None,
            new_state.value,  # e.g. PENDING
            ts,
        )
    else:
        await conn.execute(
            """
            UPDATE jobs
               SET status     = $2,
                   updated_at = COALESCE(to_timestamp($3), now())
             WHERE job_id     = $1
            """,
            job_id,
            new_state.value,  # RUNNING / SUCCEEDED / FAILED / PREEMPTED / CANCELLED
            ts,
        )


async def process_event(conn, ev):
    async with conn.transaction():
        # 1) Append to job_events
        await conn.execute(
            "INSERT INTO job_events(job_id, event_time, payload) "
            "VALUES($1, to_timestamp($2), $3::jsonb)",
            ev["job_id"], ev["timestamp"], json.dumps(ev)
        )

        # 2) Load current state from job_state (if any)
        row = await conn.fetchrow(
            "SELECT last_state FROM job_state WHERE job_id = $1",
            ev["job_id"],
        )
        current_state = JobState(row["last_state"]) if row and row["last_state"] else None

        # 3) Apply FSM transition
        new_state = apply_event(current_state, ev.get("type", ""))

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
            ev["job_id"], new_state.value, json.dumps(ev)
        )

        # 5) Optionally also update jobs table here (see next section)
        await upsert_job_row(conn, ev, new_state)



async def main():
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    consumer = AIOKafkaConsumer(
        IN_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="event-processor",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    conn = await asyncpg.connect(POSTGRES_DSN)
    await ensure_db(conn)

    await consumer.start()
    try:
        async for msg in consumer:
            event = msg.value  # dict: { event_type, job_id, ... }

            # 1) Persist to Postgres (whatever you already do)
            # await persist_to_db(event)
            await process_event(conn, msg.value)

            # 2) Publish to Redis channel for this job
            job_id = event.get("job_id")
            if job_id:
                channel = f"job_events:{job_id}"
                await r.publish(channel, json.dumps(event))
    finally:
        await consumer.stop()
        await r.aclose()
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
