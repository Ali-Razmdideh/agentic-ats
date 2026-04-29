# Reviewer Dashboard — Multi-tenant HTTP + Auth + UI

**Date:** 2026-04-29
**Sub-projects covered:** #2 (HTTP service), #3 (Auth), #4 (Reviewer UI), partial #5 (decisions table — the bare minimum the UI needs).
**Status:** Design / spec.

---

## Context

Sub-project #1 shipped a multi-tenant Postgres + MinIO storage foundation behind an org-scoped repository layer. The CLI (`ats screen`, `ats report`, `ats outreach`) writes runs through it but is single-user and offline-only.

This spec adds the **reviewer dashboard**: a separate process where authenticated reviewers can upload a JD + resumes, watch the run progress, browse the shortlist, drill into a candidate's score and citations, and accept / reject / hold candidates with comment threads. It bundles three of the originally-decomposed sub-projects (#2 HTTP service, #3 Auth, #4 UI) plus the small slice of #5 the UI needs (the `decisions` table); the heavyweight signed-audit-log piece of #5 is still deferred.

Trigger model: dashboard accepts JD + resume uploads, queues a run, and a new Python worker process picks it up via the existing orchestrator. The CLI continues to work unchanged.

---

## Decisions locked in during brainstorming

| Topic | Decision |
|---|---|
| Scope | Bundle #2 + #3 + #4 + minimal #5 in one pass. |
| Auth | Roll our own: email + password (bcrypt), HTTPOnly cookie sessions backed by a server-side `sessions` table. |
| UI stack | Next.js 15 (App Router, TypeScript) full-stack. Prisma in **introspection-only** mode (`prisma db pull`). Tailwind. |
| Run trigger | Upload + trigger from the UI. Adds a queue (status='queued' on `runs` + a Python `ats worker` daemon). |
| Schema ownership | Python SQLAlchemy stays the source of truth. New tables go in `ats/storage/models.py`. Next.js never migrates. |

---

## Top-level architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Reviewer's browser                         │
└──────────┬───────────────────────────────────┬───────────────┘
           │ HTTPS (cookie session)            │ presigned MinIO URL
           ▼                                   ▼
   ┌────────────────────────┐     ┌────────────────────────────┐
   │ Next.js (App Router)   │     │            MinIO            │
   │  dashboard/             │     │   bucket: ats-artifacts     │
   │  - login / signup       │     └────────────────────────────┘
   │  - runs list / detail   │                   ▲
   │  - upload + queue       │ raw S3 PUT (server)│
   │  - decisions / comments │                   │
   │  - Prisma client        │                   │
   └──────┬─────────────────┘ pg over local net  │
          │                                      │
          ▼                                      │
   ┌──────────────────────────────────────┐      │
   │ Postgres                             │      │
   │  - existing tables (Python-owned)    │      │
   │  - + sessions, decisions, comments   │      │
   │  - + queued_inputs/worker_id on runs │      │
   └────────────────────────────────────┬─┘      │
                                        │        │
                                        │ poll   │ download for
                                        ▼        │ parser/verifier
   ┌──────────────────────────────────────┐      │
   │ ats worker (NEW Python entrypoint)   │──────┘
   │  - claims queued runs                │
   │  - invokes existing orchestrator     │
   └──────────────────────────────────────┘
```

Three processes: Next.js (dashboard), `ats worker` (Python), `ats screen` (CLI, unchanged). One Postgres + one MinIO shared by all.

---

## Schema additions

All authored in `ats/storage/models.py` (Python, SQLAlchemy). Next.js consumes via `prisma db pull`.

```
users:
  +password_hash TEXT NULL          -- nullable so future IdP users coexist

sessions (NEW):
  id              TEXT PRIMARY KEY  -- 32-byte hex token (cookie value)
  user_id         BIGINT FK users(id) ON DELETE CASCADE
  expires_at      TIMESTAMPTZ NOT NULL
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  revoked_at      TIMESTAMPTZ NULL
  user_agent      TEXT NULL
  ip              INET NULL
  INDEX (user_id), INDEX (expires_at) WHERE revoked_at IS NULL

runs (existing, additions):
  +queued_inputs  JSONB NULL        -- {jd_blob_key, resume_blob_keys[], top_n, skip_optional}
  +worker_id      TEXT NULL
  +claimed_at     TIMESTAMPTZ NULL
  RunStatus enum  +'queued'

decisions (NEW):
  run_id, candidate_id, org_id      -- composite key, composite FKs
  decision        ENUM('shortlist','reject','hold')
  notes           TEXT NULL
  decided_by_user_id  BIGINT FK users(id)
  decided_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  PRIMARY KEY (run_id, candidate_id)
  FOREIGN KEY (org_id, run_id) REFERENCES runs(org_id, id)
  FOREIGN KEY (org_id, candidate_id) REFERENCES candidates(org_id, id)

candidate_comments (NEW):
  id              BIGINT IDENTITY PRIMARY KEY
  run_id, candidate_id, org_id
  author_user_id  BIGINT FK users(id)
  body            TEXT NOT NULL
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  composite FKs to runs / candidates as above
  INDEX (org_id, run_id, candidate_id, created_at)
```

The existing `shortlists.decision` column is retained as the **ranker's** initial recommendation (informational). Reviewer state is exclusively in `decisions`.

---

## Auth

- Hashing: **bcryptjs** (≥10 rounds). Same algorithm Python could verify later if needed.
- Session: server-side. Cookie `ats_session` carries the random 32-byte hex `session_id`; the row in `sessions` carries `user_id` + lifecycle fields. Logout sets `revoked_at`.
- Cookie attributes: `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000` (30 days).
- CSRF: SameSite=Lax handles top-level navigations. State-changing routes additionally check `Origin` against the configured `DASHBOARD_ORIGIN` env.
- Signup creates the user, auto-creates an org named after the email domain (`alice@acme.com` → org `acme`, slug `acme`, name `Acme`), and stamps the user as `admin` of that org. If the org already exists, the user joins it as `reviewer` (no invitations in v1; this is a deliberate trade-off).
- Multi-org switching: a second cookie `ats_active_org` holds the current org slug. Every protected request validates it against the user's memberships; mismatches reset to the user's first membership.

---

## Run queue + worker

**Submission path (UI):**
1. POST `/api/runs/upload` (multipart) → server validates auth + active org.
2. JD bytes streamed to MinIO via `BlobStore.put_jd(org_id, ...)` (server-side; we do not mint browser PUTs).
3. Each resume uploaded the same way; collect `file_blob_keys[]`.
4. Insert a `runs` row with `status='queued'`, `queued_inputs={jd_blob_key, resume_blob_keys, top_n, skip_optional}`, `org_id`, `created_by_user_id`.
5. Return `{ run_id }` to the browser; UI polls `/api/runs/[id]/status`.

**Worker (`ats worker`):**

```
loop every WORKER_POLL_S (default 3):
    one_row = UPDATE runs SET status='running', worker_id=$WID, claimed_at=NOW()
              WHERE id = (
                  SELECT id FROM runs
                  WHERE status='queued'
                  ORDER BY started_at
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
              )
              RETURNING id, org_id, queued_inputs;
    if none: continue
    download jd + resumes from MinIO into temp dir
    invoke run_pipeline(... pre_uploaded_blob_keys=...)
    on success: status='ok' (already set by orchestrator finish)
    on failure: status='failed' + record error in audits
```

`run_pipeline()` gains a kwarg `pre_uploaded_blob_keys` so the worker doesn't re-upload bytes already in MinIO. When set, the orchestrator skips its `blobs.put_jd` / `put_resume` steps and reuses the supplied keys.

Single worker for v1; the `FOR UPDATE SKIP LOCKED` claim makes horizontal scaling a deployment change, not a code change.

---

## UI surface

Routes (App Router):

```
/                          → redirect to /runs (if authed) or /login
/login                     → form
/signup                    → form
(protected)/
  /runs                    → list of runs in active org
  /runs/new                → upload JD + resumes form
  /runs/[id]               → run detail: candidates, decisions, status badge
  /runs/[id]/candidates/[cid] → candidate detail (parsed JSON, citations,
                                bias, comments thread, resume download)
  /settings/orgs           → org switcher
api/
  auth/login               POST
  auth/signup              POST
  auth/logout              POST
  auth/switch-org          POST
  runs/upload              POST  (multipart)
  runs/[id]/status         GET   (polling target)
  decisions                POST  (idempotent upsert)
  comments                 POST
  resumes/[blobKey]/url    GET   (mints presigned MinIO URL, 5-min expiry)
```

Components: `RunsTable`, `CandidateCard`, `DecisionPanel` (3 buttons + notes textarea), `CommentThread`, `OrgSwitcher`, `StatusBadge`. Tailwind for styling, no design system beyond defaults in v1.

Resume downloads use **presigned GET URLs** minted by the server with a 5-minute expiry — the cookie session never reaches MinIO.

---

## Code layout

```
ats/                                # existing Python (additions only)
  storage/models.py                 # +Session, +Decision, +CandidateComment,
                                    #  +queued_inputs/worker_id/claimed_at, +'queued' enum
  storage/repositories/
    sessions.py                     # NEW
    decisions.py                    # NEW
    comments.py                     # NEW
  worker.py                         # NEW: claim loop + pipeline invocation
  cli.py                            # +`ats worker` subcommand
  orchestrator.py                   # accept pre_uploaded_blob_keys

dashboard/                          # NEW Next.js 15 / App Router / TS
  package.json
  next.config.mjs
  tsconfig.json
  tailwind.config.ts
  postcss.config.mjs
  prisma/schema.prisma              # generated by `prisma db pull`
  src/
    app/
      layout.tsx, page.tsx
      login/page.tsx
      signup/page.tsx
      (protected)/
        layout.tsx                  # auth guard + nav
        runs/page.tsx
        runs/new/page.tsx
        runs/[id]/page.tsx
        runs/[id]/candidates/[cid]/page.tsx
        settings/orgs/page.tsx
      api/
        auth/login/route.ts
        auth/signup/route.ts
        auth/logout/route.ts
        auth/switch-org/route.ts
        runs/upload/route.ts
        runs/[id]/status/route.ts
        decisions/route.ts
        comments/route.ts
        resumes/[...blobKey]/url/route.ts
    lib/
      db.ts                         # Prisma singleton
      session.ts                    # cookie + sessions-table helpers
      auth.ts                       # bcrypt + login/signup, requireUser, requireOrg
      blob.ts                       # @aws-sdk/client-s3 wrapper
      repo.ts                       # tenant-scoped query helpers (mirrors OrgScopedRepository)
      schema.ts                     # zod input validation
    components/
      RunsTable.tsx
      CandidateCard.tsx
      DecisionPanel.tsx
      CommentThread.tsx
      OrgSwitcher.tsx
      StatusBadge.tsx
      Nav.tsx
    middleware.ts                   # cookie session check on (protected)/*
```

---

## Configuration

New env (consumed by Next.js):

```
DATABASE_URL          postgresql://ats:ats@localhost:5432/ats
MINIO_ENDPOINT        http://localhost:9000
MINIO_ACCESS_KEY      minioadmin
MINIO_SECRET_KEY      minioadmin
MINIO_BUCKET          ats-artifacts
MINIO_REGION          us-east-1
SESSION_COOKIE_NAME   ats_session
DASHBOARD_ORIGIN      http://localhost:3000
```

Python-side (additions to existing config):

```
ATS_WORKER_ID            hostname-pid (default)
ATS_WORKER_POLL_S        3
```

`docker-compose.yml` gains a `dashboard` service (Node 20 base, builds the Next.js app, exposes :3000) and a `worker` service (reuses the `ats:dev` image with `CMD ["worker"]`).

---

## Testing strategy

**Python:**
- Repository tests for new repos (`SessionsRepository`, `DecisionsRepository`, `CandidateCommentsRepository`) + tenant-leak guard already enforced by the collection hook.
- Worker integration test using testcontainers Postgres + FakeBlobStore: seed a queued run, run one tick of the worker loop, assert the run completes and decisions can be written.

**Next.js:**
- vitest unit tests for `lib/auth` (hash + verify, session create + revoke), `lib/session` (cookie roundtrip), `lib/repo` (org filter applied to every query).
- One Playwright happy path is **deferred**; replace with a documented manual smoke for v1: signup → upload sample JD + 2 resumes → watch run reach `ok` → open candidate → set decision → add comment.

---

## Verification (end-to-end)

1. `make dev-up` brings up Postgres + MinIO.
2. `ats init` migrates schema additions and ensures the bucket.
3. `ats worker &` starts a single worker.
4. `cd dashboard && pnpm install && pnpm dev` starts Next.js on `:3000`.
5. Browse `/signup`, create `alice@acme.com`. Auto-creates `acme` org with `alice` as admin.
6. `/runs/new` — upload `tests/fixtures/jd_ai.txt` and the four `*-cv.pdf` files. Submit.
7. Wait until status reads `ok` (worker picks it up within 3s).
8. `/runs/[id]` — see the shortlist with scores. Click a candidate.
9. `/runs/[id]/candidates/[cid]` — see parsed JSON + bias + outreach. Click "Shortlist", add a comment.
10. Verify the `decisions` row + `candidate_comments` row exist in Postgres.
11. Resume download via presigned URL works and expires in 5 minutes.
12. `pytest -q` and `pnpm test` both green.

---

## Out of scope for v1

- Password reset by email, email verification.
- Invite-by-email flows for joining an existing org.
- MFA / TOTP.
- Real-time updates (SSE/websockets) — UI uses polling at 2s while a run is running.
- Audit log surfacing in the UI (the heavy signed-log piece of sub-project #5 is still deferred).
- Mobile responsive polish, dark mode, design system beyond Tailwind defaults.
- Pagination beyond `LIMIT 50 OFFSET 0` defaults.
- Run cancellation from the UI.
- Resume PDF preview in-browser (download only for v1).
