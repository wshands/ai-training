# Audit Log & Export

AiTrainOps maintains two audit streams per tenant:

1) **Job lifecycle events** (`job_events`)
   - Job submission, start, logs, metrics, success/failure, and state changes.
2) **Admin actions** (`admin_audit_events`)
   - Token lifecycle changes and retention policy updates.

This provides a complete compliance trail: **what ran** and **who performed admin actions**.

## Admin actions captured

These actions are recorded in `admin_audit_events`:

- **token_minted** — when an admin mints a data‑plane token
- **token_revoked** — when an admin revokes a data‑plane token
- **retention_updated** — when an admin updates event retention

Each admin audit record includes:

- `tenant_id`
- `user_id`
- `action`
- `entity_type`
- `entity_id`
- `metadata`
- `created_at`

## Export endpoint

Admin export combines both streams (job events + admin actions).

```
GET /admin/audit/export?format=json
GET /admin/audit/export?format=csv
```

Response (JSON):

```json
{
  "tenant_id": "org_123",
  "events": [
    { "source": "job_event", "event_type": "JOB_SUBMITTED", ... },
    { "source": "admin_action", "action": "token_minted", ... }
  ],
  "job_events": [...],
  "admin_events": [...]
}
```

CSV export includes both sources with a `source` field and a `timestamp` column
so you can sort them together.

## Notes

- The export endpoint requires **Admin** role.
- The audit log is stored in Postgres and can be retained per tenant using the
  retention settings.
