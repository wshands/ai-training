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
    # Dependency overrides let tests inject a fake identity without hitting
    # Clerk/SSO, keeping RBAC tests fast and deterministic.
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


def test_submit_job_requires_operator(client) -> None:
    main_mod.app.dependency_overrides[main_mod.get_current_identity] = lambda: AuthContext(
        user_id="user-1",
        tenant_id="tenant-1",
        email="test@example.com",
        role="org:viewer",
    )
    resp = client.post(
        "/jobs/train",
        json={
            "model_id": "m1",
            "dataset_id": "d1",
            "epochs": 1,
            "batch_size": 8,
            "lr": 0.01,
            "distributed": False,
        },
    )
    assert resp.status_code == 403


def test_submit_job_allows_operator(client, monkeypatch) -> None:
    main_mod.app.dependency_overrides[main_mod.get_current_identity] = lambda: AuthContext(
        user_id="user-1",
        tenant_id="tenant-1",
        email="test@example.com",
        role="org:operator",
    )

    async def fake_persist(job_id: str, config: dict, tenant_id: str, user_id: str):
        assert tenant_id == "tenant-1"
        assert user_id == "user-1"

    async def fake_send_event(event):
        return None

    monkeypatch.setattr(main_mod, "persist_initial_job", fake_persist)
    monkeypatch.setattr(main_mod, "send_event", fake_send_event)

    resp = client.post(
        "/jobs/train",
        json={
            "model_id": "m1",
            "dataset_id": "d1",
            "epochs": 1,
            "batch_size": 8,
            "lr": 0.01,
            "distributed": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUBMITTED"
    assert data["job_id"]


def test_cancel_job_requires_operator(client) -> None:
    main_mod.app.dependency_overrides[main_mod.get_current_identity] = lambda: AuthContext(
        user_id="user-1",
        tenant_id="tenant-1",
        email="test@example.com",
        role="org:viewer",
    )
    resp = client.post("/jobs/job-123/cancel")
    assert resp.status_code == 403


def test_retry_job_requires_operator(client) -> None:
    main_mod.app.dependency_overrides[main_mod.get_current_identity] = lambda: AuthContext(
        user_id="user-1",
        tenant_id="tenant-1",
        email="test@example.com",
        role="org:viewer",
    )
    resp = client.post("/jobs/job-123/retry")
    assert resp.status_code == 403


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
    status = main_mod.JobState.SUBMITTED.value
    resp = client.get(f"/internal/jobs?status_filter={status}&limit=1")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing data-plane token"


def test_internal_jobs_with_data_plane_token(client, monkeypatch) -> None:
    async def fake_fetch_jobs_by_state(tenant_id: str, state: str, limit: int):
        assert tenant_id == "tenant-1"
        assert state == main_mod.JobState.SUBMITTED.value
        assert limit == 2
        return []

    monkeypatch.setattr(main_mod, "fetch_jobs_by_state", fake_fetch_jobs_by_state)
    monkeypatch.setattr(main_mod, "DATA_PLANE_TENANT_ID", "tenant-1")
    async def fake_fetch_token(tenant_id: str, token_hash: str):
        return {"id": "token-1"}
    async def fake_mark_used(token_id: str) -> None:
        assert token_id == "token-1"
    monkeypatch.setattr(main_mod, "fetch_data_plane_token", fake_fetch_token)
    monkeypatch.setattr(main_mod, "mark_data_plane_token_used", fake_mark_used)
    status = main_mod.JobState.SUBMITTED.value
    resp = client.get(
        f"/internal/jobs?status_filter={status}&limit=2",
        headers={"Authorization": "Bearer token-123"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_internal_jobs_rejects_invalid_db_token(client, monkeypatch) -> None:
    async def fake_fetch_jobs_by_state(tenant_id: str, state: str, limit: int):
        assert tenant_id == "tenant-1"
        return []

    monkeypatch.setattr(main_mod, "fetch_jobs_by_state", fake_fetch_jobs_by_state)
    monkeypatch.setattr(main_mod, "DATA_PLANE_TENANT_ID", "")
    async def fake_fetch_token(tenant_id: str, token_hash: str):
        return None
    monkeypatch.setattr(main_mod, "fetch_data_plane_token", fake_fetch_token)
    status = main_mod.JobState.SUBMITTED.value
    resp = client.get(
        f"/internal/jobs?status_filter={status}&limit=1",
        headers={
            "Authorization": "Bearer bad-token",
            "X-Tenant-Id": "tenant-1",
            "X-Agent-Id": "agent-123",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid data-plane token"


def test_admin_mint_and_list_tokens(client, monkeypatch) -> None:
    monkeypatch.setattr(main_mod, "CONTROL_PLANE_ADMIN_TOKEN", "admin-token")
    async def fake_insert(tenant_id: str, token_prefix: str, token_hash: str):
        return {
            "id": "token-1",
            "tenant_id": tenant_id,
            "token_prefix": token_prefix,
            "created_at": None,
            "last_used_at": None,
            "revoked_at": None,
        }
    async def fake_list(tenant_id: str | None = None):
        return [
            {
                "id": "token-1",
                "tenant_id": "tenant-1",
                "token_prefix": "abc12345",
                "created_at": None,
                "last_used_at": None,
                "revoked_at": None,
            }
        ]
    monkeypatch.setattr(main_mod, "insert_data_plane_token", fake_insert)
    monkeypatch.setattr(main_mod, "list_data_plane_tokens_db", fake_list)

    resp = client.post(
        "/internal/admin/data-plane-tokens",
        headers={"Authorization": "Bearer admin-token"},
        json={"tenant_id": "tenant-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "tenant-1"
    assert data["token"]
    assert data["token_prefix"]
    assert data["token_id"] == "token-1"

    resp = client.get(
        "/internal/admin/data-plane-tokens?tenant_id=tenant-1",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert resp.status_code == 200
    listed = resp.json()
    assert "tenant-1" in listed
    assert listed["tenant-1"][0]["token_prefix"] == "abc12345"


def test_admin_revoke_token(client, monkeypatch) -> None:
    monkeypatch.setattr(main_mod, "CONTROL_PLANE_ADMIN_TOKEN", "admin-token")
    async def fake_revoke(tenant_id: str, *, token_hash: str | None = None, token_id: str | None = None):
        assert tenant_id == "tenant-1"
        assert token_hash is not None
        return 1
    monkeypatch.setattr(main_mod, "revoke_data_plane_token_db", fake_revoke)

    resp = client.request(
        "DELETE",
        "/internal/admin/data-plane-tokens",
        headers={"Authorization": "Bearer admin-token"},
        json={"tenant_id": "tenant-1", "token": "token-a"},
    )
    assert resp.status_code == 200
    assert resp.json()["revoked"] == 1
