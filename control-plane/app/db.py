import asyncpg
import json
import time
from .config import POSTGRES_DSN
from typing import Any, Dict, List, Optional, Tuple


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
                updated_at TIMESTAMP,
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




async def fetch_jobs(limit: int = 100) -> List[asyncpg.Record]:
    """
    Return recent jobs.

    You can:
    - Either add a 'status' column to jobs, updated by event-processor,
    - Or compute status from job_events in a subquery.
    For now, assume jobs.status may or may not exist and default to UNKNOWN.
    """
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
              j.job_id,
              j.created_at,
              j.submitted_at,
              j.updated_at,
              j.config,
              COALESCE(j.status, 'UNKNOWN') AS status
            FROM jobs AS j
            ORDER BY j.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return rows


async def fetch_job(job_id: str) -> Optional[asyncpg.Record]:
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              j.job_id,
              j.created_at,
              j.submitted_at,
              j.updated_at,
              j.config,
              COALESCE(j.status, 'UNKNOWN') AS status
            FROM jobs AS j
            WHERE j.job_id = $1
            """,
            job_id,
        )
    return row


async def fetch_job_events_since(
    job_id: str,
    last_id: int = 0,
    limit: int = 500,
) -> List[asyncpg.Record]:
    """
    Fetch job_events for a job with id > last_id.

    event_processor.ensure_db() creates job_events with at least:
      id BIGSERIAL,
      job_id TEXT,
      event_time TIMESTAMP,
      payload JSONB

    We assume 'event_type' lives inside payload->>'event_type'.
    """
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
              id,
              job_id,
              event_time,
              payload,
              COALESCE(
                payload->>'event_type',  -- if you ever add this
                payload->>'type'         -- current data
              ) AS event_type
            FROM job_events
            WHERE job_id = $1
              AND id > $2
            ORDER BY id ASC
            LIMIT $3
            """,
            job_id,
            last_id,
            limit,
        )
    return rows
