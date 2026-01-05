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

async def process_event(conn, ev):
    await conn.execute(
        "INSERT INTO job_events(job_id, event_time, payload) VALUES($1, to_timestamp($2), $3::jsonb)",
        ev["job_id"], ev["timestamp"], json.dumps(ev)
    )
    current_state = None  # could load from DB if using state machine
    new_state = apply_event(current_state, ev.get("type", ""))
    await conn.execute(
        """INSERT INTO job_state(job_id, last_state, last_event, updated_at)
               VALUES($1,$2,$3::jsonb,now())
               ON CONFLICT(job_id) DO UPDATE
               SET last_state=EXCLUDED.last_state, last_event=EXCLUDED.last_event, updated_at=now()
        """,
        ev["job_id"], new_state.value, json.dumps(ev)
    )



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
