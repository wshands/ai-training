import asyncio, os, json
from aiokafka import AIOKafkaConsumer
import asyncpg

from state_machine import apply_event, JobState

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
IN_TOPIC = os.environ.get("KAFKA_TOPIC", "job-events")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/controlplane")

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

async def run():
    consumer = AIOKafkaConsumer(
        IN_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP.split(","),
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        group_id="event-processor",
        auto_offset_reset="earliest",
    )
    await consumer.start()
    conn = await asyncpg.connect(POSTGRES_DSN)
    await ensure_db(conn)
    try:
        async for msg in consumer:
            await process_event(conn, msg.value)
    finally:
        await consumer.stop()
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
