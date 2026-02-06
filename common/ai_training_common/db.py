"""Database access helpers for jobs and job events."""

import asyncpg
import json
import time
import uuid
from common.ai_training_common.config import POSTGRES_DSN, JOB_MAX_RETRIES
from typing import Any, Dict, List, Optional, Tuple


pool: asyncpg.pool.Pool | None = None

async def init_db():
    """Initialize the connection pool and ensure core tables exist."""
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(POSTGRES_DSN)
        async with pool.acquire() as conn:
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
            ALTER TABLE jobs
                ADD COLUMN IF NOT EXISTS retry_count INT NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS max_retries INT NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS locked_by TEXT,
                ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP;
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
            CREATE INDEX IF NOT EXISTS idx_jobs_tenant_next_run
            ON jobs(tenant_id, next_run_at);
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

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS data_plane_tokens (
                id UUID PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                token_prefix TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                last_used_at TIMESTAMP,
                revoked_at TIMESTAMP
            );
            """)

            await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_data_plane_tokens_hash
            ON data_plane_tokens(token_hash);
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_plane_tokens_tenant
            ON data_plane_tokens(tenant_id);
            """)

            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_plane_tokens_tenant_active
            ON data_plane_tokens(tenant_id, revoked_at);
            """)

    return pool


async def persist_initial_job(job_id: str, config: dict, tenant_id: str, user_id: str):
    """Insert the initial job row for a submitted job."""
    global pool
    if pool is None:
        await init_db()
    max_retries = config.get("max_retries")
    if max_retries is None:
        max_retries = JOB_MAX_RETRIES
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO jobs(job_id, tenant_id, user_id, submitted_at, config, retry_count, max_retries, next_run_at)
                   VALUES($1, $2, $3, to_timestamp($4), $5::jsonb, $6, $7, now())""",
            job_id,
            tenant_id,
            user_id,
            config.get("submitted_at", int(time.time())),
            json.dumps(config),
            0,
            int(max_retries),
        )


async def fetch_jobs(tenant_id: str, limit: int = 100, offset: int = 0) -> List[asyncpg.Record]:
    """Fetch a page of job summaries for a tenant."""
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
            OFFSET $3
            """,
            tenant_id,
            limit,
            offset,
        )
    return rows


async def fetch_jobs_by_state(
    tenant_id: str,
    state: str,
    limit: int = 100,
) -> List[asyncpg.Record]:
    """Fetch jobs for a tenant filtered by last_state."""
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
              AND COALESCE(js.last_state, 'SUBMITTED') = $2
            ORDER BY j.created_at ASC
            LIMIT $3
            """,
            tenant_id,
            state,
            limit,
        )
    return rows


async def fetch_job(tenant_id: str, job_id: str):
    """Fetch a single job and its latest state for a tenant."""
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
    """Fetch job events with IDs greater than last_id."""
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


async def fetch_job_events_before(
    tenant_id: str,
    job_id: str,
    before_id: int,
    limit: int = 500,
) -> List[asyncpg.Record]:
    """Fetch job events with IDs less than before_id (descending)."""
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
            AND id < $3
            ORDER BY id DESC
            LIMIT $4
            """,
            tenant_id,
            job_id,
            before_id,
            limit,
        )
    return rows


async def fetch_job_events_latest(
    tenant_id: str,
    job_id: str,
    limit: int = 200,
) -> List[asyncpg.Record]:
    """Fetch the newest job events for a job (descending)."""
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
            ORDER BY id DESC
            LIMIT $3
            """,
            tenant_id,
            job_id,
            limit,
        )
    return rows


async def claim_jobs(
    tenant_id: str,
    agent_id: str,
    limit: int,
    *,
    lock_timeout_seconds: int,
) -> List[asyncpg.Record]:
    """Atomically claim ready jobs for a tenant and return their summaries."""
    global pool
    if pool is None:
        await init_db()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH candidates AS (
                SELECT j.job_id
                FROM jobs AS j
                WHERE j.tenant_id = $1
                  AND COALESCE(
                        (SELECT js.last_state FROM job_state AS js WHERE js.job_id = j.job_id),
                        'SUBMITTED'
                      ) IN ('SUBMITTED', 'RETRYING')
                  AND (j.next_run_at IS NULL OR j.next_run_at <= now())
                  AND (
                        j.locked_at IS NULL
                        OR j.locked_at < now() - ($4::int || ' seconds')::interval
                      )
                ORDER BY j.created_at ASC
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            UPDATE jobs AS j
               SET locked_by = $3,
                   locked_at = now(),
                   updated_at = now(),
                   next_run_at = NULL
            FROM candidates AS c
            WHERE j.job_id = c.job_id
            RETURNING
              j.job_id,
              j.created_at,
              j.submitted_at,
              j.updated_at,
              j.config,
              (SELECT js.last_event FROM job_state AS js WHERE js.job_id = j.job_id) AS last_event,
              COALESCE((SELECT js.last_state FROM job_state AS js WHERE js.job_id = j.job_id), 'SUBMITTED') AS status
            """,
            tenant_id,
            limit,
            agent_id,
            lock_timeout_seconds,
        )
    return rows


async def data_plane_tokens_exist(tenant_id: str) -> bool:
    """Return True if any active data-plane tokens exist for a tenant."""
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM data_plane_tokens
            WHERE tenant_id = $1
              AND revoked_at IS NULL
            """,
            tenant_id,
        )
    return bool(count and int(count) > 0)


async def fetch_data_plane_token(tenant_id: str, token_hash: str) -> Optional[asyncpg.Record]:
    """Fetch a data-plane token row by tenant and hash."""
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, tenant_id, token_prefix, token_hash, created_at, last_used_at, revoked_at
            FROM data_plane_tokens
            WHERE tenant_id = $1
              AND token_hash = $2
              AND revoked_at IS NULL
            """,
            tenant_id,
            token_hash,
        )
    return row


async def list_data_plane_tokens(tenant_id: Optional[str] = None) -> List[asyncpg.Record]:
    """List data-plane tokens (optionally filtered by tenant)."""
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        if tenant_id:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, token_prefix, token_hash, created_at, last_used_at, revoked_at
                FROM data_plane_tokens
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                """,
                tenant_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, token_prefix, token_hash, created_at, last_used_at, revoked_at
                FROM data_plane_tokens
                ORDER BY tenant_id ASC, created_at DESC
                """
            )
    return rows


async def insert_data_plane_token(
    tenant_id: str,
    token_prefix: str,
    token_hash: str,
) -> asyncpg.Record:
    """Insert a data-plane token (idempotent if token_hash exists)."""
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT id, tenant_id, token_prefix, token_hash, created_at, last_used_at, revoked_at
            FROM data_plane_tokens
            WHERE token_hash = $1
            """,
            token_hash,
        )
        if existing:
            if existing["tenant_id"] != tenant_id:
                raise ValueError("Token already exists for a different tenant")
            if existing["revoked_at"] is not None:
                await conn.execute(
                    """
                    UPDATE data_plane_tokens
                    SET revoked_at = NULL
                    WHERE id = $1
                    """,
                    existing["id"],
                )
            return await conn.fetchrow(
                """
                SELECT id, tenant_id, token_prefix, token_hash, created_at, last_used_at, revoked_at
                FROM data_plane_tokens
                WHERE id = $1
                """,
                existing["id"],
            )
        token_id = uuid.uuid4()
        row = await conn.fetchrow(
            """
            INSERT INTO data_plane_tokens(id, tenant_id, token_prefix, token_hash)
            VALUES($1, $2, $3, $4)
            RETURNING id, tenant_id, token_prefix, token_hash, created_at, last_used_at, revoked_at
            """,
            token_id,
            tenant_id,
            token_prefix,
            token_hash,
        )
    if row is None:
        raise RuntimeError("Failed to insert data-plane token")
    return row


async def revoke_data_plane_token(
    tenant_id: str,
    *,
    token_hash: Optional[str] = None,
    token_id: Optional[str] = None,
) -> int:
    """Revoke a data-plane token (by hash or id) or all for a tenant."""
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        if token_id:
            result = await conn.execute(
                """
                UPDATE data_plane_tokens
                SET revoked_at = now()
                WHERE tenant_id = $1
                  AND id = $2
                  AND revoked_at IS NULL
                """,
                tenant_id,
                token_id,
            )
        elif token_hash:
            result = await conn.execute(
                """
                UPDATE data_plane_tokens
                SET revoked_at = now()
                WHERE tenant_id = $1
                  AND token_hash = $2
                  AND revoked_at IS NULL
                """,
                tenant_id,
                token_hash,
            )
        else:
            result = await conn.execute(
                """
                UPDATE data_plane_tokens
                SET revoked_at = now()
                WHERE tenant_id = $1
                  AND revoked_at IS NULL
                """,
                tenant_id,
            )
    try:
        return int(result.split(" ")[-1])
    except Exception:
        return 0


async def mark_data_plane_token_used(token_id: str) -> None:
    """Update last_used_at for a token."""
    global pool
    if pool is None:
        await init_db()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE data_plane_tokens
            SET last_used_at = now()
            WHERE id = $1
            """,
            token_id,
        )
