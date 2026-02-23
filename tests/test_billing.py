"""Billing guard tests."""

import pytest
from fastapi import HTTPException

from app import main as main_mod
from app.main import AuthContext


def _identity() -> AuthContext:
    return AuthContext(
        user_id="user-1",
        tenant_id="tenant-1",
        email="test@example.com",
        role="org:member",
    )


@pytest.mark.anyio
async def test_paid_guard_allows_active(monkeypatch) -> None:
    monkeypatch.setattr(main_mod, "BILLING_ENFORCEMENT", True)

    async def fake_fetch(tenant_id: str):
        assert tenant_id == "tenant-1"
        return {"status": "active"}

    monkeypatch.setattr(main_mod, "fetch_tenant_billing", fake_fetch)
    identity = _identity()
    result = await main_mod._ensure_paid(identity)
    assert result is identity


@pytest.mark.anyio
async def test_paid_guard_blocks_inactive(monkeypatch) -> None:
    monkeypatch.setattr(main_mod, "BILLING_ENFORCEMENT", True)

    async def fake_fetch(tenant_id: str):
        assert tenant_id == "tenant-1"
        return {"status": "canceled"}

    monkeypatch.setattr(main_mod, "fetch_tenant_billing", fake_fetch)
    with pytest.raises(HTTPException) as exc:
        await main_mod._ensure_paid(_identity())
    assert exc.value.status_code == 402


@pytest.mark.anyio
async def test_paid_guard_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(main_mod, "BILLING_ENFORCEMENT", False)

    async def fake_fetch(_tenant_id: str):
        raise AssertionError("fetch_tenant_billing should not be called")

    monkeypatch.setattr(main_mod, "fetch_tenant_billing", fake_fetch)
    identity = _identity()
    result = await main_mod._ensure_paid(identity)
    assert result is identity
