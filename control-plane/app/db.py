import asyncpg
import json
import time
from .config import POSTGRES_DSN

pool: asyncpg.pool.Pool | None = None

async def init_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(POSTGRES_DSN)
        async with pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT now(),
                submitted_at TIMESTAMP,
                config JSONB NOT NULL,
                status TEXT DEFAULT 'SUBMITTED'
            );
            """)
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS job_events (
                id BIGSERIAL PRIMARY KEY,
                job_id TEXT NOT NULL,
                event_time TIMESTAMP,
                payload JSONB
            );
            """)
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS job_state (
                job_id TEXT PRIMARY KEY,
                last_state TEXT,
                last_event JSONB,
                updated_at TIMESTAMP
            );
            """)
    return pool

async def persist_initial_job(job_id: str, config: dict):
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO jobs(job_id, submitted_at, config)
                   VALUES($1, to_timestamp($2), $3::jsonb)""",
            job_id,
            config.get("submitted_at", int(time.time())),
            json.dumps(config),
        )
