# Data-plane Authentication Model

This document describes how the control-plane and data-plane authenticate and how
the `API token`, `agent_id`, and `tenant_id` are used together.

## Overview

The data-plane (job-launcher + training jobs) does not talk to Kafka directly.
Instead it calls internal control-plane endpoints:

- `GET /internal/jobs` to fetch jobs to run
- `POST /internal/events` to publish lifecycle events

Those endpoints are protected by a shared data-plane token and scoped to a
tenant. This keeps the control-plane as the system of record for job scheduling
and enforces tenant isolation.

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

The control-plane accepts the token in one of two ways:

1) **Single token** (legacy/simple):
   - `DATA_PLANE_API_TOKEN` is a single shared token.
2) **Token rotation map** (recommended):
   - `DATA_PLANE_API_TOKENS` is a JSON map of tenant -> list of tokens.
   - This lets you rotate tokens per tenant without downtime.

Example:

```
DATA_PLANE_API_TOKENS='{"org_123": ["old-token", "new-token"]}'
```

### agent_id (`DATA_PLANE_AGENT_ID`)

The agent identifies a specific launcher instance and is used for auditing,
rate limiting, and targeted revocation in the future.

The launcher sends it as:

```
X-Agent-Id: <agent_id>
```

By default the agent id is the pod hostname, but you can set
`DATA_PLANE_AGENT_ID` for a stable identifier across restarts.

## Request flow

1) Launcher polls `GET /internal/jobs`.
   - Headers:
     - `Authorization: Bearer <token>`
     - `X-Tenant-Id: <tenant_id>`
     - `X-Agent-Id: <agent_id>`
2) Control-plane validates:
   - Token is valid for the tenant (single token or rotation map).
   - Tenant matches `DATA_PLANE_TENANT_ID` if configured.
3) Launcher receives jobs and emits `JOB_PENDING` via `POST /internal/events`.
4) Control-plane publishes events to Kafka and updates job state.

## Advantages

- **Clear enforcement point**: only the control-plane can issue official jobs.
- **Tenant isolation**: each data-plane is pinned to a tenant.
- **Operational simplicity**: no Kafka access from customer clusters.
- **Safe rotation**: multiple tokens per tenant allow zero-downtime rotation.
- **Auditability**: agent ids identify which launcher is making requests.

## Common configurations

### Single tenant, single token

```
DATA_PLANE_TENANT_ID=org_123
DATA_PLANE_API_TOKEN=local-dev-token
```

### Multi-token rotation (per tenant)

```
DATA_PLANE_API_TOKENS='{"org_123":["token-a","token-b"]}'
DATA_PLANE_TENANT_ID=org_123
```

## Notes

- Header names are case-insensitive (`X-Agent-Id` vs `x-agent-id`).
- If `DATA_PLANE_API_TOKENS` is set, the single `DATA_PLANE_API_TOKEN` is ignored.
- Use `DATA_PLANE_LOG_POLLS=false` to disable poll logging in the control-plane.

## Admin endpoints (manual token minting)

Use these endpoints to mint or list tokens without editing env vars by hand.
Protect them with `CONTROL_PLANE_ADMIN_TOKEN`.

- `GET /internal/admin/data-plane-tokens?tenant_id=<id>`
- `POST /internal/admin/data-plane-tokens` with JSON body:

```json
{ "tenant_id": "org_123" }
```

Send the admin token as:

```
Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>
```

Note: tokens are stored in-process and, if Redis is available, persisted in
Redis under the `data_plane_tokens` key.

### How it works (short explanation)

The admin endpoints use `CONTROL_PLANE_ADMIN_TOKEN` (bearer auth). On a `POST`,
the control-plane loads the current token map (from Redis if present, otherwise
from in-process memory), generates a token if needed, appends it to the tenant,
and writes the updated map back to Redis. The data-plane auth path always checks
the Redis-backed map first and falls back to the single `DATA_PLANE_API_TOKEN`
only if the map is empty.

### Example usage

Mint a token for a tenant:

```bash
curl -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_123"}' \
  http://localhost:8000/internal/admin/data-plane-tokens
```

List tokens for a tenant:

```bash
curl -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  "http://localhost:8000/internal/admin/data-plane-tokens?tenant_id=org_123"
```

Sample response:

```json
{
  "org_123": [
    "token-abc",
    "token-def"
  ]
}
```

Revoke a token for a tenant (If token is omitted, it clears all tokens for the tenant.):

```bash
curl -X DELETE -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_123","token":"token-abc"}' \
  http://localhost:8000/internal/admin/data-plane-tokens
```

Add a token for a tenant

```bash
curl -H "Authorization: Bearer <CONTROL_PLANE_ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"org_...","token":"another-token"}' \
  http://localhost:8000/internal/admin/data-plane-tokens
```
