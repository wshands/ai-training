import asyncpg
import json
import time
from common.ai_training_common.config import POSTGRES_DSN
from typing import Any, Dict, List, Optional, Tuple


pool: asyncpg.pool.Pool | None = None

async def init_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(POSTGRES_DSN)
        async with pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT now()
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT now()
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS memberships (
                tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
                user_id TEXT NOT NULL REFERENCES users(user_id),
                role TEXT NOT NULL DEFAULT 'owner',
                created_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (tenant_id, user_id)
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT now(),
                submitted_at TIMESTAMP,
                updated_at TIMESTAMP,
                config JSONB NOT NULL
            );
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_created_at_desc
            ON jobs(created_at DESC);
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_tenant_created_at_desc
            ON jobs(tenant_id, created_at DESC);
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS job_events (
                id BIGSERIAL PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                job_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                seq BIGINT,
                event_type TEXT NOT NULL,
                producer TEXT,
                schema_version INT,
                event_time TIMESTAMP NOT NULL DEFAULT now(),
                payload JSONB NOT NULL DEFAULT '{}'::jsonb
            );
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_events_job_id_id
            ON job_events(job_id, id);
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_events_tenant_job_id_id
            ON job_events(tenant_id, job_id, id);
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_events_job_id_seq
            ON job_events(job_id, seq);
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS job_state (
            job_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            last_state TEXT NOT NULL DEFAULT 'SUBMITTED',
            last_event JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_event_id TEXT,
            last_seq BIGINT,
            updated_at TIMESTAMP NOT NULL DEFAULT now()
            );

            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_state_updated_at_desc
            ON job_state(updated_at DESC);
            """)

    return pool


async def persist_initial_job(job_id: str, config: dict, tenant_id: str, user_id: str):
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO jobs(job_id, tenant_id, user_id, submitted_at, config)
                   VALUES($1, $2, $3, to_timestamp($4), $5::jsonb)""",
            job_id,
            tenant_id,
            user_id,
            config.get("submitted_at", int(time.time())),
            json.dumps(config),
        )


async def fetch_jobs(tenant_id: str, limit: int = 100) -> List[asyncpg.Record]:
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
              COALESCE(js.updated_at, j.updated_at) AS updated_at,
              j.config,
              js.last_event,
              COALESCE(js.last_state, 'SUBMITTED') AS status
            FROM jobs AS j
            LEFT JOIN job_state AS js
              ON js.job_id = j.job_id
            WHERE j.tenant_id = $1
            ORDER BY j.created_at DESC
            LIMIT $2
            """,
            tenant_id,
            limit,
        )
    return rows


async def fetch_job(tenant_id: str, job_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              j.job_id,
              j.tenant_id,
              j.user_id,
              j.created_at,
              j.submitted_at,
              j.updated_at,
              j.config,
              COALESCE(js.last_state, 'UNKNOWN') AS status
            FROM jobs AS j
            LEFT JOIN job_state AS js
              ON js.job_id = j.job_id
            WHERE j.tenant_id = $1
              AND j.job_id = $2
            """,
            tenant_id,
            job_id,
        )
        return row


async def fetch_job_events_since(
    tenant_id: str,
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
            tenant_id,
            user_id,
            event_time,
            event_type,
            seq,
            producer,
            schema_version,
            payload
            FROM job_events
            WHERE tenant_id = $1
            AND job_id = $2
            AND id > $3
            ORDER BY id ASC
            LIMIT $4
            """,
            tenant_id,
            job_id,
            last_id,
            limit,
        )
    return rows


async def fetch_job_event_types_until(
    tenant_id: str,
    job_id: str,
    up_to_id: int,
) -> List[str]:
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_type
            FROM job_events
            WHERE tenant_id = $1
            AND job_id = $2
            AND id <= $3
            ORDER BY id ASC
            """,
            tenant_id,
            job_id,
            up_to_id,
        )
    return [r["event_type"] for r in rows]
