# Threat Model (MVP)

This document describes the initial threat model for AiTrainOps and the
security boundaries of the control‑plane and data‑plane.

## System boundaries

- **Control‑plane (vendor‑hosted)**: API, UI, Postgres, event bus, Redis.
- **Data‑plane (customer‑hosted)**: Kubernetes job launcher + training jobs.
- **Data never leaves the customer’s VPC** except telemetry (events/logs/metrics).

## Trust assumptions

- Customers control their own cluster, VPC, and data storage.
- The control‑plane is trusted for orchestration and metadata only.
- The data‑plane must authenticate to the control‑plane via API tokens.

## Primary threats & mitigations

### 1) Unauthorized access to jobs or logs
**Threat**: An attacker gains access to another tenant’s jobs or logs.  
**Mitigations**:
- Tenant‑scoped auth (Clerk org claims).
- RBAC enforcement at API + UI (admin/operator/viewer).
- Data‑plane token authentication per tenant.

### 2) Token leakage / misuse
**Threat**: A data‑plane token is leaked and used to impersonate a launcher.  
**Mitigations**:
- Tokens stored as hashes in Postgres.
- Token prefix stored for troubleshooting.
- Admin‑only mint/revoke UI.
- Last‑used timestamp for detection + rotation.

### 3) Control‑plane compromise
**Threat**: Control‑plane is compromised, attacker attempts data access.  
**Mitigations**:
- No direct access to customer data or storage.
- Only metadata and telemetry stored in control‑plane.
- Least‑privilege IAM for cloud resources.

### 4) Data‑plane compromise
**Threat**: A compromised launcher sends false events or floods the API.  
**Mitigations**:
- Authentication via tenant tokens.
- Job claim leases prevent duplicate execution.
- Event retention + audit history for detection.

### 5) Audit tampering
**Threat**: Admin actions are not traceable or are modified.  
**Mitigations**:
- Job events persisted in Postgres.
- Admin actions written to `admin_audit_events`.
- Export includes both job history and admin actions.

## Data classification

- **Customer data**: never stored in control‑plane.
- **Telemetry data**: job metadata, logs, metrics, events.
- **Credentials**: only token hashes stored; no raw token persists.

## Security roadmap

- Private connectivity options (VPC endpoints / PrivateLink).
- Dedicated tenant encryption keys for audit/event storage.
- WAF / rate‑limit controls on public API.

