"""Billing webhook tests."""

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.main import AuthContext


def _fake_event(event_type: str, data_obj: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "data": {"object": data_obj}}


@pytest.fixture
def client(monkeypatch):
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


def _patch_webhook_verifier(monkeypatch, event_payload: dict[str, Any]) -> None:
    monkeypatch.setattr(main_mod, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(main_mod, "STRIPE_WEBHOOK_SECRET", "whsec_test")

    def fake_construct_event(payload, sig_header, secret):
        return event_payload

    monkeypatch.setattr(main_mod.stripe.Webhook, "construct_event", fake_construct_event)


def test_webhook_checkout_completed_upserts_billing(client, monkeypatch) -> None:
    calls = {}

    async def fake_upsert(tenant_id, **kwargs):
        calls["tenant_id"] = tenant_id
        calls.update(kwargs)

    monkeypatch.setattr(main_mod, "upsert_tenant_billing", fake_upsert)

    fake_sub = {
        "items": {"data": [{"price": {"id": "price_123"}}]},
        "status": "active",
        "current_period_end": int(time.time()) + 3600,
        "cancel_at_period_end": False,
    }
    monkeypatch.setattr(main_mod.stripe.Subscription, "retrieve", lambda *args, **kwargs: fake_sub)

    event = _fake_event(
        "checkout.session.completed",
        {
            "client_reference_id": "tenant-1",
            "subscription": "sub_123",
            "customer": "cus_123",
        },
    )
    _patch_webhook_verifier(monkeypatch, event)
    resp = client.post("/billing/webhook", data=json.dumps(event), headers={"stripe-signature": "t"})
    assert resp.status_code == 200
    assert calls["tenant_id"] == "tenant-1"
    assert calls["stripe_customer_id"] == "cus_123"
    assert calls["stripe_subscription_id"] == "sub_123"
    assert calls["stripe_price_id"] == "price_123"
    assert calls["status"] == "active"


def test_webhook_subscription_update_updates_billing(client, monkeypatch) -> None:
    calls = {"by_sub": None, "by_customer": None}

    async def fake_update_by_sub(sub_id, **kwargs):
        calls["by_sub"] = (sub_id, kwargs)

    async def fake_update_by_customer(customer_id, **kwargs):
        calls["by_customer"] = (customer_id, kwargs)

    monkeypatch.setattr(main_mod, "update_billing_by_subscription", fake_update_by_sub)
    monkeypatch.setattr(main_mod, "update_billing_by_customer", fake_update_by_customer)

    event = _fake_event(
        "customer.subscription.updated",
        {
            "id": "sub_999",
            "customer": "cus_999",
            "items": {"data": [{"price": {"id": "price_999"}}]},
            "status": "past_due",
            "current_period_end": int(time.time()) + 7200,
            "cancel_at_period_end": True,
        },
    )
    _patch_webhook_verifier(monkeypatch, event)
    resp = client.post("/billing/webhook", data=json.dumps(event), headers={"stripe-signature": "t"})
    assert resp.status_code == 200
    assert calls["by_sub"][0] == "sub_999"
    assert calls["by_customer"][0] == "cus_999"
