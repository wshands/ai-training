"""API-level tests with FastAPI TestClient."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.main import AuthContext


@pytest.fixture
def client():
    main_mod.app.router.on_startup.clear()
    main_mod.app.router.on_shutdown.clear()
    main_mod.app.dependency_overrides.clear()
    main_mod.app.dependency_overrides[main_mod.get_current_identity] = lambda: AuthContext(
        user_id="user-1",
        tenant_id="tenant-1",
        email="test@example.com",
        role="org:member",
    )
    return TestClient(main_mod.app)


def test_list_jobs_returns_summaries(client, monkeypatch) -> None:
    async def fake_fetch_jobs(tenant_id: str, limit: int, offset: int):
        assert tenant_id == "tenant-1"
        assert limit == 2
        assert offset == 1
        return [
            {
                "job_id": "job-1",
                "created_at": None,
                "submitted_at": None,
                "updated_at": None,
                "config": {"model_id": "m1", "dataset_id": "d1"},
                "last_event": {"error": {"message": "boom"}},
                "status": "FAILED",
            },
            {
                "job_id": "job-2",
                "created_at": None,
                "submitted_at": None,
                "updated_at": None,
                "config": {"model_id": "m2", "dataset_id": "d2"},
                "last_event": {},
                "status": "RUNNING",
            },
        ]

    monkeypatch.setattr(main_mod, "fetch_jobs", fake_fetch_jobs)
    resp = client.get("/jobs?limit=2&offset=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["job_id"] == "job-1"
    assert data[0]["status"] == "FAILED"
    assert data[0]["last_error"]["message"] == "boom"
    assert data[1]["job_id"] == "job-2"


def test_latest_events_no_state(client, monkeypatch) -> None:
    async def fake_fetch_latest(tenant_id: str, job_id: str, limit: int):
        assert tenant_id == "tenant-1"
        assert job_id == "job-123"
        assert limit == 2
        now = datetime.now(timezone.utc)
        return [
            {
                "id": 10,
                "job_id": "job-123",
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "event_time": now,
                "event_type": "JOB_LOG",
                "seq": 1,
                "producer": "test",
                "schema_version": 1,
                "payload": {"message": "hello"},
            },
            {
                "id": 11,
                "job_id": "job-123",
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "event_time": now,
                "event_type": "JOB_FAILED",
                "seq": 2,
                "producer": "test",
                "schema_version": 1,
                "payload": {"error": {"message": "boom"}},
            },
        ]

    monkeypatch.setattr(main_mod, "fetch_job_events_latest", fake_fetch_latest)
    resp = client.get("/jobs/job-123/events/latest?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["event_type"] == "JOB_LOG"
    assert "state" not in data[0]


def test_internal_jobs_requires_data_plane_token(client, monkeypatch) -> None:
    async def fake_fetch_jobs_by_state(tenant_id: str, state: str, limit: int):
        return []

    monkeypatch.setattr(main_mod, "fetch_jobs_by_state", fake_fetch_jobs_by_state)
    resp = client.get("/internal/jobs?status_filter=SUBMITTED&limit=1")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "DATA_PLANE_API_TOKEN not configured"


def test_internal_jobs_with_data_plane_token(client, monkeypatch) -> None:
    async def fake_fetch_jobs_by_state(tenant_id: str, state: str, limit: int):
        assert tenant_id == "tenant-1"
        assert state == "SUBMITTED"
        assert limit == 2
        return []

    monkeypatch.setattr(main_mod, "fetch_jobs_by_state", fake_fetch_jobs_by_state)
    monkeypatch.setattr(main_mod, "DATA_PLANE_API_TOKEN", "token-123")
    monkeypatch.setattr(main_mod, "DATA_PLANE_TENANT_ID", "tenant-1")
    resp = client.get(
        "/internal/jobs?status_filter=SUBMITTED&limit=2",
        headers={"Authorization": "Bearer token-123"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
