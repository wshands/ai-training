# RBAC (Role-Based Access Control)

AITrainOps enforces organization-scoped RBAC using **Clerk org roles**. Roles are
read from the Clerk session and normalized into one of:

- `admin`
- `operator`
- `viewer`

Defaults:
- Clerk’s `org:member` is treated as `operator` for MVP workflows.

## Role meanings

- **Admin**: full access, including admin endpoints.
- **Operator**: can create/cancel/retry jobs and view all job data.
- **Viewer**: read-only access to jobs, events, and streams.

## Backend guards

The control plane uses `require_min_role(...)` to protect endpoints:

**Operator**
- `POST /jobs/train`
- `POST /jobs/{job_id}/cancel`
- `POST /jobs/{job_id}/retry`

**Viewer**
- `GET /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/events`
- `GET /jobs/{job_id}/events/latest`
- `GET /ws/jobs`
- `GET /ws/jobs/{job_id}`

**Admin**
- `/internal/admin/*` (admin token–based)

## UI gating

The UI hides or disables actions based on role:

- **Operator+**: "New Job" button, submit/cancel/retry
- **Viewer**: read‑only access (can view jobs and logs)

## Notes

- Roles are currently **not** stored in Postgres.
- Clerk permissions are **not** used (roles only).
- If you need custom role sets or permission matrices, implement them in Clerk
  or add a DB-backed role model.

## Testing RBAC

API tests use FastAPI dependency overrides to inject fake identities. This
avoids hitting Clerk/SSO during tests and keeps RBAC checks deterministic.
See `tests/test_api.py` for examples overriding `get_current_identity` with
viewer/operator roles.
