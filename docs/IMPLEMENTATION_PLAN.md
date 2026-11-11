# TenderOS V1 – Implementation plan

Scope: V1 only (personalised tenders, eligibility, relevance scoring, 8-hour reanalysis,
WhatsApp alerts). V1.5/V2/V3 are kept as extension seams, not built.

## Repository state at start

Empty directory, no git history. Nothing to preserve.

Local environment observed: Node 26, pnpm 11, Python 3.12, PostgreSQL 18 (Homebrew,
running), pgvector package present. **Docker and Redis are not installed**, so the
Compose stack is written but could not be exercised here; local development runs
Postgres natively and uses filesystem object storage.

## Architecture

```
apps/web     Next.js App Router · TS strict · Tailwind v4 · Radix (shadcn-style) · TanStack Query · RHF + Zod
apps/api     FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL 16+
apps/worker  asyncio scheduler reusing api domain services (00:00/08:00/16:00 IST + 09:00 IST digest)
storage      S3-compatible (MinIO in Compose) or local filesystem backend
```

Key decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Auth | Email + password (argon2id), opaque session token in httpOnly cookie, SHA-256 hash stored server-side | No third-party IdP needed for V1; easy to swap for OIDC later |
| Tenancy | Active company stored on the server-side session; every company-owned query filters by `session.organization_id` | Client never supplies `company_id` |
| Web→API | Next.js rewrites `/api/*` to FastAPI | Same-origin cookies, no CORS credentials |
| CSRF | SameSite=Lax cookie + required `X-Requested-With: tenderos` header on unsafe methods | Defence in depth |
| Scheduler | Postgres-backed slot table with unique `(job, slot_key)` (idempotent), no Redis | Brief allows a "comparably simple documented scheduler"; one fewer moving part |
| Money | `BIGINT` paise | No floats |
| Time | `timestamptz` UTC, rendered Asia/Kolkata | |
| Tender visibility | Demo/authorised-feed tenders are global; manual imports are visible only to the importing company | Imports are made under that company's attestation |

## Milestones

1. **Foundation** – monorepo, Compose, env, DB models + Alembic migration, design system.
2. **First runnable milestone** – auth, onboarding wizard (persisted per step), 24 DEMO tenders,
   dashboard, explorer (search/filter/sort/paginate, URL-synced), tender detail with
   eligibility evidence, notification preview, source health.
3. **Engines** – deterministic eligibility (PASS/FAIL/UNKNOWN/NOT_APPLICABLE), relevance score
   (25/15/15/20/15/10), match persistence and evidence.
4. **Ingestion** – SourceAdapter interface; DemoFixture, ManualCSV (mapping, validation,
   duplicates, history), ManualDocument (PDF via PyMuPDF, BOQ via openpyxl, requirement
   extraction with page + quote, human review); OfficialFeed and MPPublicHomepage defined
   but disabled.
5. **Scheduler + notifications** – 8-hourly reanalysis, 48h reminders, deadline-change
   alerts, 09:00 IST digest, outbox, simulated transport, Meta Cloud API transport,
   webhook verification, opt-out, quiet hours.
6. **QA** – backend integration tests, frontend tests, docs.

## Status (11 Nov 2026)

| Milestone | Status |
| --- | --- |
| 1 Foundation | Done. 27 tables in a single Alembic migration (`0001`) |
| 2 First runnable milestone | Done. Every route loads through the Next proxy (smoke-tested with curl) |
| 3 Engines | Done. Covered by unit and integration tests |
| 4 Ingestion | Done. Official feed and MP homepage adapters are disabled by design |
| 5 Scheduler + notifications | Done. Simulated transport verified; Meta transport covered by tests with a fake client only |
| 6 QA | 57 backend tests, 21 frontend tests, tsc, eslint, ruff and `next build` all pass. Compose stack not run (no Docker) |

## Extension seams

- `services/ingestion/base.py::SourceAdapter` – new feeds plug in here.
- `services/extraction/ai.py::AIExtractor` – provider-neutral; disabled unless configured.
- `tender_documents` + pgvector extension reserved for V1.5 document compliance search.
- `company_experience` / `tender_versions` keep history needed for V2 financial analysis.
