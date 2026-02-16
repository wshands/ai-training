"""Integration tests for auto-retry using a real Postgres container."""

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

import common.ai_training_common.db as db
from common.ai_training_common.events import EventType, JobEventIn

import event_processor as ep


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    container = PostgresContainer("postgres:15-alpine")
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        user = container.username
        password = container.password
        db_name = container.dbname
        yield f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    finally:
        container.stop()


@pytest.mark.anyio
async def test_auto_retry_creates_new_job_with_backoff(postgres_dsn, monkeypatch) -> None:
    monkeypatch.setattr(db, "POSTGRES_DSN", postgres_dsn)
    db.pool = None
    await db.init_db()

    monkeypatch.setattr(ep, "JOB_RETRY_BASE_SECONDS", 1)
    monkeypatch.setattr(ep, "JOB_RETRY_MAX_SECONDS", 2)

    conn = await asyncpg.connect(postgres_dsn)
    await db.configure_json_codecs(conn)
    try:
        job_id = "job-1"
        tenant_id = "tenant-1"
        user_id = "user-1"
        config = {"model_id": "m1", "max_retries": 3}

        await conn.execute(
            """
            INSERT INTO jobs(job_id, tenant_id, user_id, submitted_at, updated_at, config, retry_count, max_retries, next_run_at)
            VALUES($1, $2, $3, now(), now(), $4::jsonb, $5, $6, now())
            """,
            job_id,
            tenant_id,
            user_id,
            config,
            0,
            3,
        )

        event = JobEventIn(
            event_type=EventType.JOB_FAILED,
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=user_id,
            seq=2,
            producer="test-suite",
            payload={"error": {"message": "boom"}},
        )

        await ep.process_event(conn, event)

        rows = await conn.fetch(
            "SELECT job_id, next_run_at, config FROM jobs WHERE tenant_id=$1",
            tenant_id,
        )
        assert len(rows) == 2
        new_row = next(r for r in rows if r["job_id"] != job_id)
        new_job_id = new_row["job_id"]

        assert new_row["config"]["retry_of"] == job_id
        assert new_row["config"]["retry_attempt"] == 1

        delay = await conn.fetchval(
            "SELECT EXTRACT(EPOCH FROM (next_run_at - now())) FROM jobs WHERE job_id=$1",
            new_job_id,
        )
        assert delay is not None
        assert delay >= 0
        assert delay <= 5

        submitted = await conn.fetchval(
            """
            SELECT event_type FROM job_events
            WHERE job_id=$1
            ORDER BY id DESC
            LIMIT 1
            """,
            new_job_id,
        )
        assert submitted == "JOB_SUBMITTED"

        retry_count = await conn.fetchval(
            "SELECT retry_count FROM jobs WHERE job_id=$1",
            job_id,
        )
        assert retry_count == 1
    finally:
        await conn.close()
