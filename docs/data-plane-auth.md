# Data-plane Authentication Model

This document describes how the control-plane and data-plane authenticate and
how the API token is stored and validated.

## Overview

The data-plane (job-launcher + training jobs) does not talk to Kafka directly.
Instead it calls internal control-plane endpoints:

- `POST /internal/jobs/claim` to atomically claim jobs to run
- `GET /internal/jobs` to query jobs by state (cancel checks)
- `POST /internal/events` to publish lifecycle events

Those endpoints are protected by a shared data-plane token and scoped to a
tenant. This keeps the control-plane as the system of record for job scheduling
and enforces tenant isolation.

The control-plane requires tokens to exist in Postgres; env token fallbacks are
not supported.

## Concepts

### tenant_id (`DATA_PLANE_TENANT_ID`)

The tenant represents the customer (Clerk organization) whose jobs are being
executed. In the control-plane, `tenant_id` is derived from the Clerk JWT:

- `org_id` if the user is acting in an organization
- `sub` (user id) if no organization is active

The data-plane launcher is configured with the tenant it serves:

- `DATA_PLANE_TENANT_ID=<org_id>`

This ensures that a launcher only receives jobs for its assigned tenant.
If the tenant id does not match, the control-plane rejects the request.

### API token (`DATA_PLANE_API_TOKEN`)

The token authenticates the launcher to the control-plane. It is sent on every
internal request as a bearer token:

```
Authorization: Bearer <token>
```

The token is minted via the admin API and stored hashed in Postgres. The
data-plane reads the plaintext token from its environment and sends it on
requests; the control-plane does not accept env-based token fallbacks.

### Token hashing + storage (Postgres)

Tokens are stored in Postgres in the `data_plane_tokens` table. The control-plane
never stores raw tokens. Instead it stores:

- `token_hash`: HMAC-SHA256 of the token using `DATA_PLANE_TOKEN_PEPPER`
- `token_prefix`: first 8 characters of the token for display/debugging
- `created_at`, `last_used_at`, `revoked_at`

Purpose of hashing:

- Prevents plaintext tokens from being stored at rest
- Allows rotation and revocation without exposing secrets
- Enables simple audit metadata (last used, created)

Validation flow:

1) Control-plane extracts the bearer token.
2) It computes `token_hash` using `DATA_PLANE_TOKEN_PEPPER`.
3) It looks up an active (not revoked) token for the tenant.
4) If found, request is authorized and `last_used_at` is updated.

Important:

- `DATA_PLANE_TOKEN_PEPPER` must be set and identical across all control-plane
  instances. Changing it invalidates all existing tokens.

### agent_id (`DATA_PLANE_AGENT_ID`)

The agent identifies a specific launcher instance and is used for auditing,
rate limiting, and targeted revocation in the future.

The launcher sends it as:

```
X-Agent-Id: <agent_id>
```

By default the agent id is the pod hostname, but you can set
`DATA_PLANE_AGENT_ID` for a stable identifier across restarts.

## Admin endpoints (token minting)

These endpoints are protected by `CONTROL_PLANE_ADMIN_TOKEN`.

- `POST /internal/admin/data-plane-tokens`  
  Mint a new token (or register a provided token) for a tenant.
- `GET /internal/admin/data-plane-tokens?tenant_id=<id>`  
  List token metadata (prefix/created/last_used) for a tenant.
- `DELETE /internal/admin/data-plane-tokens`  
  Revoke a token by `token` or `token_id`, or revoke all for a tenant.

Mint a token:

```bash
curl -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_123"}' \
  https://<control-plane>/internal/admin/data-plane-tokens
```

Register a provided token:

```bash
curl -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_123","token":"my-fixed-token"}' \
  https://<control-plane>/internal/admin/data-plane-tokens
```

Response (token is returned once):

```json
{
  "tenant_id": "org_123",
  "token": "plain-text-token",
  "token_id": "uuid",
  "token_prefix": "plain-te"
}
```

List tokens (metadata only):

```bash
curl -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  "https://<control-plane>/internal/admin/data-plane-tokens?tenant_id=org_123"
```

Revoke a token (by token or token_id):

```bash
curl -X DELETE -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_123","token":"plain-text-token"}' \
  https://<control-plane>/internal/admin/data-plane-tokens
```

Revoke by token_id:

```bash
curl -X DELETE -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_123","token_id":"uuid"}' \
  https://<control-plane>/internal/admin/data-plane-tokens
```

Revoke all tokens for a tenant:

```bash
curl -X DELETE -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_123"}' \
  https://<control-plane>/internal/admin/data-plane-tokens
```

## Advantages

- Clear enforcement point: only the control-plane issues tokens
- Tenant isolation: each data-plane is pinned to a tenant
- Safe rotation: tokens can be minted and revoked without downtime
- Auditability: last-used timestamps and prefixes are stored
