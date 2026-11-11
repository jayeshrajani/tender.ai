# TenderOS

Tender intelligence for construction contractors in **Madhya Pradesh**. TenderOS shows which public works tenders your company is likely eligible for, cites the NIT page and clause behind each criterion, and lists the evidence you still need. Relevance scoring and WhatsApp alerts are kept separate from eligibility.

> **This is V1.** Bid readiness (V1.5), bid preparation and financial history (V2) and competitor benchmarking (V3) are not built. Seams for them are listed under [Future milestones](#future-milestones).

## What is real and what is DEMO

| Area | State |
| --- | --- |
| Tender data | **24 fictional DEMO tenders** (labelled `DEMO` everywhere) plus whatever your team imports manually. None of it is live government data. |
| MP eProcurement / CPPP / GeM | **Not connected.** No verified public APIs exist. Automated collection is **disabled** until written authorisation is in place. |
| Manual CSV / PDF / XLSX import | Works. The operator attests they accessed the portal and solved any CAPTCHA themselves. |
| WhatsApp | **SIMULATED** by default. Messages go to an outbox and are never sent. Live sending needs Meta credentials *and* `TENDEROS_WHATSAPP_MODE=live`. |
| Eligibility & relevance | Real, deterministic engines. They run over DEMO and imported data. |
| Scheduler | Real. Runs at 00:00, 08:00 and 16:00 IST, with a digest at 09:00 IST. |

The UI never shows "Live", "Synced" or "All tenders".

## Quick start (local, no Docker)

Requirements: Python 3.11+ (3.12 tested), Node 20+ (26 tested), pnpm 9+, PostgreSQL 15+ running on `localhost` (pg_trgm required; pgvector optional). All dependencies come from the public npm registry and PyPI.

```bash
git clone https://github.com/jayeshrajani/tender.ai.git && cd tender.ai
cp .env.example .env            # optional; defaults work locally
pnpm setup                      # venv + deps + create DBs + migrate + seed DEMO data
pnpm dev                        # API :8010, worker, web :3010
```

Open http://localhost:3010. DEMO logins (password = `TENDEROS_DEMO_SEED_PASSWORD`, default `tenderos-demo-2026`, **local only**):

| Email | Company | Role |
| --- | --- | --- |
| owner@narmada.demo | Narmada Buildcon Pvt. Ltd. (DEMO) | owner |
| analyst@narmada.demo | Narmada Buildcon Pvt. Ltd. (DEMO) | analyst |
| viewer@narmada.demo | Narmada Buildcon Pvt. Ltd. (DEMO) | viewer |
| owner@malwa.demo | Malwa Jal Infra LLP (DEMO) | owner (second tenant, used to check tenant isolation) |

DEMO dates are offsets from an anchor date. To move them forward so the deadlines are in the future again, run `pnpm seed:reanchor`.

Individual processes: `pnpm dev:api`, `pnpm dev:worker`, `pnpm dev:web`, `pnpm seed`.

## Quick start (Docker Compose)

```bash
cp .env.example .env
docker compose up --build -d                     # postgres(pgvector:pg16), minio, api, worker, web
docker compose run --rm api python -m app.seed   # DEMO data
```

Redis is in the Compose file under the `queue` profile (`docker compose --profile queue up`). It is reserved for a future job queue; the V1 worker does not use it. **The Compose stack was written but not run here, because Docker was not available in the build environment.**

## Checks

```bash
pnpm test:api       # 57 backend integration tests (needs local Postgres; uses DB "tenderos_test")
pnpm test:web       # 21 frontend tests (Vitest + Testing Library)
pnpm lint           # eslint + ruff
pnpm typecheck      # tsc --noEmit (strict)
pnpm --filter @tenderos/web build
```

## Architecture

```
apps/web     Next.js 16 App Router · TS strict · Tailwind v4 · Radix primitives (shadcn-style, owned in src/components/ui)
             TanStack Query · React Hook Form + Zod · Geist. /api/* is rewritten to FastAPI so cookies stay same-origin.
             Kokonut UI (shadcn registry, src/components/kokonutui): ⌘K palette, account menu, theme switch, file upload.
             Light/dark/system theme via next-themes; colours are tokens in globals.css redefined under .dark.
             Geist for UI text, Bricolage Grotesque (self-hosted via @fontsource) for headings; cobalt brand accent,
             with green reserved for eligible / PASS / verified.
apps/api     FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL (pg_trgm; pgvector reserved)
  app/services/eligibility.py     deterministic eligibility engine
  app/services/scoring.py         relevance score (documented weights)
  app/services/ingestion/         SourceAdapter, adapters, normalise/version/dedupe pipeline, CSV + document import
  app/services/extraction/        PyMuPDF text, openpyxl BOQ, English+Hindi criteria parser, provider-neutral AI seam
  app/services/notifications/     templates, simulated + Meta transports, outbox, webhook
  app/services/jobs.py            idempotent scheduled jobs (used by worker and the manual "Run reanalysis")
apps/worker  Scheduler loop; imports app.* services
```

### Authentication and tenancy

- Email and password, hashed with **argon2id**. The session is a random token in an `httpOnly`, `SameSite=Lax` cookie, and only its SHA-256 hash is stored (`auth_sessions`).
- The **active company is held in the server-side session**. Every company-owned query filters on `session.organization_id` after re-checking membership. The client never sends a `company_id`.
- Roles: `owner > admin > analyst > viewer` (see `/settings/team`). Invitations are one-time links that expire after 7 days. V1 does not send email.
- CSRF protection: the SameSite cookie, plus a required `X-Requested-With: tenderos` header on every mutating request. The WhatsApp webhook is exempt because it is HMAC-verified instead.
- Tenders are global. **Manual imports are private** to the importing company (`tenders.visibility_org_id`), and so are uploaded tender documents.
- Files are served only through signed links that expire after 5 minutes. Each link is bound to the company and still needs a valid session.

## Eligibility rules

Each requirement is evaluated to `PASS`, `FAIL`, `UNKNOWN` (shown as *Needs verification*) or `NOT_APPLICABLE`.

| Overall status | Rule |
| --- | --- |
| `NOT_ELIGIBLE` | At least one **mandatory**, **source-verified** criterion FAILs against the company's own recorded data. |
| `ELIGIBLE` | Every mandatory criterion PASSes, every criterion is source-verified, and every piece of supporting evidence is verified and unexpired on the submission date. |
| `NEEDS_VERIFICATION` | Anything else, including when no criteria have been extracted at all. |

Further rules:

- An expired or unverified certificate never PASSes. Expiry is checked against the **bid deadline**, not today's date.
- Automatically extracted criteria are `needs_review`. Until a person confirms them, they can only lead to NEEDS_VERIFICATION, never to a confirmed failure or ELIGIBLE.
- AI output (when enabled) can only add `needs_review` criteria whose quote appears verbatim on the cited page. It can never override a deterministic failure.
- The UI states that results do not guarantee acceptance by the procuring authority.

## Relevance score (0–100)

Relevance is computed separately from eligibility. A NOT_ELIGIBLE tender stays NOT_ELIGIBLE however high it scores.

| Factor | Weight | Rule |
| --- | --- | --- |
| Specialisation | 25 | Category match = 0.8; with matching subcategory or specialty = 1.0; related category = 0.4 |
| Location | 15 | Preferred district = 1.0; within operating radius (approximate district HQ distance) = 0.5–0.9; statewide = 0.4 |
| Value suitability | 15 | Inside min/max = 1.0; outside, scaled down by distance from the range |
| Similar experience | 20 | CPWD-style: best of one work ≥ 80 %, two ≥ 60 % or three ≥ 40 % of the estimate; related categories score half |
| Operational capacity | 15 | Mean of concurrent-project headroom and annualised value as a share of turnover |
| Time to prepare | 10 | ≥ 14 days = 1.0 · 7–14 days = 0.7 · 3–7 days = 0.4 · 1–3 days = 0.15 · under 1 day = 0.05 · closed = 0 |

## Ingestion

The `SourceAdapter` interface provides `discover(since)`, `fetch_metadata(id)`, `fetch_documents(id)`, `fetch_changes(id)` and `health()`.

| Adapter | Status |
| --- | --- |
| `DemoFixtureAdapter` | Enabled. Idempotent: an unchanged fixture produces "unchanged", not a new version. |
| `ManualCSVImportAdapter` | Enabled. Supports column mapping, row validation, in-file and cross-source duplicate detection, run history and per-row errors. |
| `ManualDocumentImportAdapter` | Enabled. PDF (PyMuPDF) and XLSX BOQ (openpyxl, cached values only; `.xlsm` and files containing `vbaProject.bin` are rejected). Extracts metadata, criteria with page, clause and quote, and corrigendum deadline changes. |
| `OfficialFeedAdapter` | **Disabled.** Needs `authorization_reference`, `integration_documentation`, `credentials_configured` and `permitted_usage` in the source config, plus `permission_status=authorized`. No endpoint is assumed. |
| `MPPublicHomepageAdapter` | **Disabled.** Partial coverage only. Never solves or bypasses CAPTCHA. |

Every tender stores its provenance: source URL, source organisation, tender ID, retrieval method, operator, import time, permission status, original file SHA-256 and the source run. Unique identity is `(source, source_tender_id, visibility)`. Cross-source duplicates are linked through `duplicate_of_id` and keep their own provenance. Changes create `tender_versions` rows that record the changed fields and previous values.

Scheduler: `job_runs(job, slot_key)` is unique, so each slot runs once even with several workers or restarts. On start-up the worker catches up on the most recent missed slot. Unauthorised sources are recorded as `skipped`, together with the reason.

## WhatsApp

- Uses the official Meta Cloud API only: `POST https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages`.
- Template bodies are in `services/notifications/templates.py::TEMPLATE_DEFINITIONS`. Submitting them to `POST /{API_VERSION}/{WABA_ID}/message_templates` and getting them approved is a manual operations step.
- Alerts:
  - a daily digest at 09:00 IST
  - deadline-change alerts (from corrigenda)
  - a reminder 48 hours before closing
- Alerts are de-duplicated by `company:tender:type:recipient`.
- Messages are sent only to recipients who opted in. Replying `STOP` opts the recipient out. Quiet hours hold messages until the window ends. Stored payloads keep only masked phone numbers.
- Webhook:
  - `GET` verifies `hub.verify_token`.
  - `POST` verifies `X-Hub-Signature-256`.
  - Delivery callbacks are idempotent on `(message_id, status)`.

## API (TenderOS's own endpoints, not government endpoints)

OpenAPI docs at http://localhost:8010/docs.

```
GET  /health
POST /api/v1/auth/register | login | logout | switch-company | accept-invite      GET /api/v1/auth/me
GET  /api/v1/sources                      GET  /api/v1/ingestion/runs
POST /api/v1/ingestion/csv/preview        POST /api/v1/ingestion/import          POST /api/v1/ingestion/run
GET  /api/v1/tenders  (q, district[], category[], eligibility[], action[], min_value, max_value,
                       closing_within, changed_within, min_score, saved, include_closed, sort, order, page, page_size)
GET  /api/v1/tenders/facets               GET  /api/v1/dashboard
GET  /api/v1/tenders/{id} | /documents | /eligibility | /match
POST /api/v1/tenders/{id}/save            POST /api/v1/tenders/{id}/notes
PATCH /api/v1/tenders/{id}/requirements/{rid}   (human review of extracted criteria)
GET|PUT /api/v1/company/profile           GET  /api/v1/company/reference
POST|DELETE /api/v1/company/experience    POST /api/v1/company/documents   GET /api/v1/company/documents
PATCH /api/v1/company/certificates/{id}/verification   GET /api/v1/company/documents/{id}/link
GET|PUT /api/v1/notifications/preferences GET /api/v1/notifications/outbox | /preview   POST /api/v1/notifications/test
GET|POST /api/v1/whatsapp/webhook
GET  /api/v1/team   POST /api/v1/team/invitations   PATCH|DELETE /api/v1/team/members/{id}   GET /api/v1/team/audit
GET|POST|DELETE /api/v1/views             GET /api/v1/files/{signed-token}
```

## Data authorisation risks

- The MP eProcurement policy page says reproduction may require written permission. Get legal review before any automated collection or redistribution.
- Manual imports depend on what the operator attests. Imports stay private to the importing company and are never shown to other tenants.
- For an official feed, contact NIC technical support (support-eproc@nic.in). This is a contact address, not an API.
- GST, Udyam, MCA and PWD registry checks are done by people. TenderOS records only who marked a certificate as verified and when.
- See [docs/SOURCE_REGISTRY.md](docs/SOURCE_REGISTRY.md).

## Known limitations

- Docker Compose and the MinIO backend were **not exercised** here (no Docker). Local runs use filesystem storage.
- No OCR. Scanned PDFs without a text layer produce a warning and need manual criteria.
- The Hindi parser covers common NIT phrasing. Unusual wording falls back to manual review.
- Bid capacity (A×N×2 − B) is always "Needs verification" because it is not computed.
- District coordinates for the radius preference are approximate district headquarters.
- No email delivery for invitations or password reset. Invite links are shared by hand, and there is no password reset flow yet.
- Login rate limiting is in-process. Use a shared limiter, such as Redis or the gateway, when running several instances.
- A manual "Run reanalysis now" recomputes every tenant. That is acceptable for V1 scale.
- Phone verification is shown but not yet implemented as an OTP or reply flow.

## Future milestones

- **V1.5 – Bid readiness:** per-tender document checklists built from `tender_requirements` and certificates, plus pgvector search over `tender_documents` (the extension is already created).
- **V2 – Bid preparation and financial history:** BOQ rate analysis against the SoR (the reference source is in the registry), and turnover history from `company_experience`.
- **V3 – Competitor benchmarking:** only from lawful public award data (MP Tender Status / Archive), once authorised.
- Official feed client in `OfficialFeedAdapter`, once NIC/government authorisation and a written specification exist.
- Email notifications, OTP phone verification, SSO/OIDC.
