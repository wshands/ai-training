# Third-Party Services

This document explains external services used by AITrainOps outside the core
control-plane/data-plane runtime, why they are used, and how they are wired.

## Scope

- Focuses on operational, auth, billing, and go-to-market services.
- Complements existing service-specific docs (for example, billing and RBAC).

## Service Inventory

## Cloudflare Pages (marketing site)

- Purpose: host low-cost static marketing site (`landing-lite`) at
  `www.aitrainops.com`.
- Why used:
  - no always-on compute cost for marketing pages
  - simple GitHub-connected deploy flow
  - fast global CDN for static assets
- How used:
  - source: `landing-lite/`
  - custom domain mapped to `www`
  - app product remains separate at `app.aitrainops.com` (AWS-hosted UI)
- Data handled: public website assets only.

## Formspree (pilot request form)

- Purpose: no-backend form handling for pilot requests from marketing site.
- Why used:
  - avoids building/operating a dedicated contact-form API
  - stores/tracks submissions and forwards to inbox
- How used:
  - HTML form action in `landing-lite/index.html`
  - form includes `_subject` and `_next` to return with `?submitted=1`
  - fallback `mailto:` remains available
- Data handled:
  - visitor-provided contact fields (name, work email, company, use case)

## Clerk (authentication and org-scoped identity)

- Purpose: sign-in, JWT issuance, org claims, role context.
- Why used:
  - managed auth with organization support and JWT flow
  - reduces custom auth surface area
- How used:
  - UI uses Clerk SDK for sign-in/session
  - API validates Clerk JWT and extracts org/user role claims
  - RBAC uses normalized roles (`admin`, `operator`, `viewer`)
- Related docs:
  - `docs/rbac.md`
  - `docs/architecture-overview.md`

## Stripe (billing)

- Purpose: subscription checkout, portal, and billing state sync.
- Why used:
  - managed subscription lifecycle and payment compliance tooling
- How used:
  - API creates checkout/portal sessions
  - webhook updates internal tenant billing state
  - admin UI routes users into Stripe-hosted flows
- Related doc:
  - `docs/billing.md`

## GitHub + GitHub Actions (source + CI/CD)

- Purpose: source control, builds, deploy automation.
- Why used:
  - standard SaaS delivery workflow with auditable pipeline history
- How used:
  - workflows build and publish images/artifacts
  - OIDC role assumption for AWS deploy permissions
- Related docs/scripts:
  - `.github/workflows/`
  - `docs/ci-integration.md`
  - `scripts/setup-github-ci.sh`

## DNS and registrar services

- Purpose: domain registration + DNS hosting.
- Current operating model:
  - Route 53 is authoritative DNS for runtime records (`app`, `api`, email TXT/MX)
  - `www` points to Cloudflare Pages target
  - apex redirect (`aitrainops.com` -> `www`) is optional and can be added later
- Why called out:
  - split registrar/DNS setups can cause confusion if nameservers do not match
    intended authoritative provider.

## Google Workspace (business email)

- Purpose: domain email inboxes/aliases (for example `admin@`, `support@`).
- Why used:
  - professional sender identity and domain ownership alignment
- How used:
  - outbound/inbound business communication and form notification destination
  - DNS MX/SPF/DKIM/DMARC must stay valid when changing DNS providers.

## Optional GTM/CRM tools (for example, HubSpot)

- Purpose: contact management, campaign tracking, sales pipeline workflows.
- Why used:
  - structured outreach at scale beyond ad-hoc spreadsheets
- Status:
  - optional for early design-partner phase
  - can remain lightweight until outreach volume justifies subscription.

## Security and data minimization guidance

- Only collect fields needed for partner qualification.
- Keep secrets out of client-side source and committed env files.
- Review each vendor's data retention, privacy, and breach-notification policies.
- Restrict admin access with MFA and least privilege.
- Document data flows for compliance reviews and customer questionnaires.

## Change management guidance

- Before adopting a new third-party service:
  - define owner
  - document purpose and data handled
  - document failure mode and fallback plan
  - add/update docs in this file and any service-specific runbooks
