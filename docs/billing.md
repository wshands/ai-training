# Billing (Stripe Checkout + Portal)

This document describes the billing flow for AITrainOps using Stripe Checkout,
Customer Portal, and webhooks.

## Overview

We use Stripe to manage subscriptions:

- **Checkout** creates a new subscription.
- **Customer Portal** lets customers manage payment method/cancel.
- **Webhooks** keep the control-plane DB in sync with Stripe.
- **Admin UI** shows status and routes users to Stripe.

Billing is enforced server-side when `BILLING_ENFORCEMENT=true`.

## Configuration

Environment variables (control-plane):

```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
BILLING_ENFORCEMENT=false
```

Notes:
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` should be stored in Secrets Manager for AWS.
- `STRIPE_PRICE_ID` is not secret and can live in Terraform tfvars.
- `BILLING_ENFORCEMENT=true` requires an active subscription for paid endpoints.

## Data model

Table: `tenant_billing`

Fields:
- `tenant_id`
- `stripe_customer_id`
- `stripe_subscription_id`
- `stripe_price_id`
- `status` (active, trialing, past_due, canceled, etc.)
- `current_period_end`
- `cancel_at_period_end`

## DB helper functions

These helpers are defined in `common/ai_training_common/db.py` and are used by
webhooks, `/billing/sync`, and the Admin UI.

### `upsert_tenant_billing(...)`
- **Purpose:** Insert/update the billing row for a tenant (authoritative write).
- **Used by:** `checkout.session.completed` webhook and `POST /billing/sync`.
- **Why:** Those flows know the tenant_id and should (re)write the canonical row.

### `update_billing_by_subscription(subscription_id, ...)`
- **Purpose:** Update a billing row by Stripe subscription id.
- **Used by:** `customer.subscription.*` webhook events.
- **Why:** Stripe subscription events often do **not** include tenant_id.

### `update_billing_by_customer(customer_id, ...)`
- **Purpose:** Update a billing row by Stripe customer id.
- **Used by:** `customer.subscription.*` webhook events.
- **Why:** Provides a second mapping path if subscription_id wasn’t stored yet or
  webhook ordering is different than expected.

### `fetch_tenant_billing(tenant_id)`
- **Purpose:** Read the billing row for the tenant.
- **Used by:** `/billing/status`, Admin UI, and billing enforcement guard.

## API endpoints

### `POST /billing/checkout`
Creates a Stripe Checkout Session (subscription).

Request body:
```json
{ "return_url": "https://aitrainops.com/admin/tokens" }
```

Response:
```json
{ "url": "https://checkout.stripe.com/..." }
```

### `POST /billing/portal`
Creates a Stripe Customer Portal session.

Request body:
```json
{ "return_url": "https://aitrainops.com/admin/tokens" }
```

Response:
```json
{ "url": "https://billing.stripe.com/..." }
```

### `GET /billing/status`
Returns current billing status for the tenant.

Response:
```json
{
  "tenant_id": "org_123",
  "status": "active",
  "current_period_end": "2026-03-01T00:00:00Z",
  "cancel_at_period_end": false
}
```

### `POST /billing/sync`
Re-sync billing from Stripe by searching for subscriptions that have
`metadata.tenant_id` set to the current tenant. This is useful after a control-plane
rebuild or DB reset.

Response:
```json
{
  "tenant_id": "org_123",
  "status": "active",
  "current_period_end": "2026-03-01T00:00:00Z",
  "cancel_at_period_end": false
}
```

### `POST /billing/webhook`
Stripe webhook receiver. Processes:
- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`

## Webhook setup

Stripe Dashboard → Developers → Webhooks:

- Endpoint: `https://api.aitrainops.com/billing/webhook`
- Events:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`

Copy the signing secret (`whsec_...`) into `STRIPE_WEBHOOK_SECRET`.

## Enforcement

When `BILLING_ENFORCEMENT=true`, these endpoints require a paid subscription
(`active`, `trialing`, or `past_due`):

- `POST /jobs/train`
- `POST /jobs/{job_id}/cancel`
- `POST /jobs/{job_id}/retry`
- `POST /admin/data-plane-tokens`
- `DELETE /admin/data-plane-tokens/{token_id}`
- `PUT /admin/settings/retention`

Read-only endpoints (jobs list/detail/events) remain accessible.

## Local testing

Use Stripe test keys and Stripe CLI:

```
stripe listen --forward-to localhost:8000/billing/webhook
```

Set:
```
STRIPE_WEBHOOK_SECRET=whsec_...
```

You can keep `BILLING_ENFORCEMENT=false` during development.

## Admin UI flow

The Admin billing card in the UI uses `GET /billing/status` to show a badge
and renewal date. It also exposes two actions:

- **Start subscription** → calls `POST /billing/checkout`
- **Manage billing** → calls `POST /billing/portal`

When the status is `active`, `trialing`, or `past_due`, the Start Subscription
button is disabled and shows “Subscription active.”

Important: subscriptions should be started from the Admin UI so the Checkout
Session includes `tenant_id` metadata. That is how the webhook maps the Stripe
subscription back to the tenant.
