"""Billing sync endpoint tests."""

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
        role="org:admin",
    )
    return TestClient(main_mod.app)


def test_billing_sync_upserts_and_returns_status(client, monkeypatch) -> None:
    monkeypatch.setattr(main_mod, "STRIPE_SECRET_KEY", "sk_test_fake")

    class FakeSearch:
        data = [
            {
                "id": "sub_123",
                "customer": "cus_123",
                "status": "active",
                "created": 1234567890,
                "current_period_end": 1700000000,
                "cancel_at_period_end": False,
                "items": {"data": [{"price": {"id": "price_123"}}]},
            }
        ]

    monkeypatch.setattr(
        main_mod.stripe.Subscription,
        "search",
        lambda **_kwargs: FakeSearch(),
        raising=False,
    )

    calls = {}

    async def fake_upsert(tenant_id, **kwargs):
        calls["tenant_id"] = tenant_id
        calls.update(kwargs)

    async def fake_fetch(tenant_id):
        assert tenant_id == "tenant-1"
        return {
            "tenant_id": tenant_id,
            "status": "active",
            "current_period_end": datetime(2026, 3, 1, tzinfo=timezone.utc),
            "cancel_at_period_end": False,
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_123",
            "stripe_price_id": "price_123",
        }

    monkeypatch.setattr(main_mod, "upsert_tenant_billing", fake_upsert)
    monkeypatch.setattr(main_mod, "fetch_tenant_billing", fake_fetch)

    resp = client.post("/billing/sync")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "active"
    assert calls["tenant_id"] == "tenant-1"
    assert calls["stripe_customer_id"] == "cus_123"
    assert calls["stripe_subscription_id"] == "sub_123"
    assert calls["stripe_price_id"] == "price_123"
