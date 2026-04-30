# ATS — AI-Powered Resume Screening

[![CI](https://github.com/aliRazmdideh/ats/actions/workflows/ci.yml/badge.svg)](https://github.com/aliRazmdideh/ats/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ats-screen.svg)](https://pypi.org/project/ats-screen/)
[![Python](https://img.shields.io/pypi/pyversions/ats-screen.svg)](https://pypi.org/project/ats-screen/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A multi-agent system for screening resumes against a job description, with a
**reviewer dashboard** for hiring managers. Built on the
[Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/python). Runs
against the native Anthropic API or any compatible endpoint (OpenRouter is the
tested alternative).

**Three runtimes, one Postgres + MinIO:**

- `ats screen` — original CLI, drops resumes through 13 cooperating subagents.
- `ats worker` — background daemon that pulls queued runs from Postgres
  (`FOR UPDATE SKIP LOCKED`) and processes them with the same orchestrator.
- `dashboard/` — Next.js 15 (App Router, TypeScript) reviewer UI: signup /
  login, JD + resumes upload, live pipeline progress, score gauge with
  pros/cons distillation, rich agent-output visualizations, and shortlist /
  hold / reject decisions with comment threads.

13 cooperating subagents — parser, jd_analyzer, matcher, ranker, verifier,
bias_auditor, deduper, taxonomy, summarizer, red_flags, interview_qs, outreach,
enricher — orchestrated through one `ClaudeSDKClient` with bounded concurrency,
structured logging, retry-with-backoff, schema validation on every output, and
per-run USD cost accounting.

Persists to **Postgres** (results, audits, decisions, comments, sessions,
orgs / users / memberships) and **MinIO** (resume + JD blobs) behind an
org-scoped repository layer — multi-tenant from day one.

---

## Install

### From PyPI

```bash
pip install ats-screen
```

### From source

```bash
git clone https://github.com/aliRazmdideh/ats
cd ats
pip install -e ".[dev]"
```

### Docker

```bash
docker pull ghcr.io/alirazmdideh/ats:latest
# or build it yourself
docker build -t ats:dev .
```

---

## Configure

Copy `.env.example` → `.env` and fill in.

### Anthropic native

```env
ANTHROPIC_API_KEY=sk-ant-...
ATS_MODEL_SMART=claude-sonnet-4-5
ATS_MODEL_FAST=claude-haiku-4-5
```

### OpenRouter (any Anthropic-compatible provider)

```env
ANTHROPIC_BASE_URL=https://openrouter.ai/api
ANTHROPIC_API_KEY=sk-or-v1-...
ATS_MODEL_SMART=anthropic/claude-sonnet-4.5
ATS_MODEL_FAST=anthropic/claude-haiku-4.5
```

> The Claude Code CLI bundled with the SDK honors `ANTHROPIC_BASE_URL`. The
> trailing `/v1/messages` is appended by the SDK — set the base URL to
> `https://openrouter.ai/api` (no `/v1` suffix).

### All settings

| Env var | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | API key (or OpenRouter key with the base URL above) |
| `ANTHROPIC_BASE_URL` | Anthropic | Override endpoint (e.g. OpenRouter) |
| `ATS_PG_DSN` | `postgresql+asyncpg://ats:ats@localhost:5432/ats` | Async Postgres DSN |
| `ATS_PG_POOL_SIZE` | `10` | SQLAlchemy pool size |
| `ATS_PG_POOL_MAX_OVER` | `20` | SQLAlchemy max overflow |
| `ATS_MINIO_ENDPOINT` | `http://localhost:9000` | S3-compatible endpoint URL (MinIO or AWS S3) |
| `ATS_MINIO_ACCESS_KEY` | `minioadmin` | Access key |
| `ATS_MINIO_SECRET_KEY` | `minioadmin` | Secret key |
| `ATS_MINIO_BUCKET` | `ats-artifacts` | Bucket holding resumes + JDs |
| `ATS_MINIO_REGION` | `us-east-1` | Required by boto3 even for MinIO |
| `ATS_DEFAULT_ORG_SLUG` | `system` | Org used by the CLI (until auth lands) |
| `ATS_INBOX_DIR` | `./inbox` | Default resume drop directory |
| `ATS_MODEL_SMART` | `anthropic/claude-sonnet-4.5` | Used by matcher / verifier / bias_auditor / interview_qs |
| `ATS_MODEL_FAST` | `anthropic/claude-haiku-4.5` | Used by parser / dedup / ranker / taxonomy / etc. |
| `ATS_BIAS_BLOCK_THRESHOLD` | `0.20` | Cohort score gap that triggers a `block` |
| `ATS_AGENT_TIMEOUT_S` | `120.0` | Per-agent invocation timeout |
| `ATS_AGENT_MAX_RETRIES` | `2` | Retries on transient errors |
| `ATS_CONCURRENCY` | `4` | Max parallel subagent calls |
| `ATS_MAX_COST_USD` | `0` | Hard cap (`0` = no cap) |
| `ATS_WORKER_POLL_S` | `3` | Worker queue poll interval |
| `WORKER_HTTP_PROXY` | _(unset)_ | Optional HTTP/HTTPS proxy for the worker container — set when the host's outbound traffic must go through one (e.g. `http://host.docker.internal:11180`). Blank in any environment with direct egress. |
| `ATS_AUDIT_HMAC_KEY` | _(zeros, dev only)_ | Hex-encoded 32-byte secret for the `audit_log` HMAC chain. Worker + dashboard MUST share the same value. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |

---

## Usage

Bring up Postgres + MinIO locally (one-time):

```bash
make dev-up        # docker compose up -d (Postgres on :5432, MinIO on :9000/:9001)
ats init           # creates schema, seeds the default org, ensures the bucket
```

`ats init` is idempotent: it runs `CREATE EXTENSION IF NOT EXISTS citext`, then
SQLAlchemy's `create_all` to build the schema, seeds the default org from
`ATS_DEFAULT_ORG_SLUG` (defaults to `system`), and ensures the MinIO bucket
exists. There is no separate migration tool — schema lives in
[`ats/storage/models.py`](ats/storage/models.py).

Then:

```bash
ats screen --jd path/to/jd.txt --resumes path/to/resumes/ --top 5 [--org acme]
ats report --run 1 --cost [--org acme]
ats outreach --run 1 --decision shortlist [--org acme]
```

`--org` defaults to the `ATS_DEFAULT_ORG_SLUG` env var (`system`).

### Dashboard

The Next.js reviewer dashboard in [`dashboard/`](dashboard/) wraps the same
Postgres + MinIO that the CLI uses. Hiring managers sign up, upload a JD +
CV bundle, watch the pipeline run, and review each candidate without ever
touching the CLI.

#### Run everything via Docker (recommended)

```bash
make dev-up                                              # Postgres + MinIO
docker build -t ats:dev .                                # Python image (CLI + worker)
docker build -t ats-dashboard:dev dashboard              # Next.js image
docker compose --profile app up -d                       # adds worker + dashboard
ats init                                                 # one-time: schema + bucket
```

Endpoints (host-side, default ports):

| Service | URL | Notes |
|---|---|---|
| Reviewer dashboard | http://localhost:3000 | Next.js 15 production build |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| MinIO S3 API | http://localhost:9000 | What the worker + dashboard speak |
| Postgres | `localhost:5432` | `ats` / `ats` / `ats` |

#### Run the dashboard from source (fast iteration)

```bash
make dev-up
ats init
ats worker &                                             # one shell
cd dashboard
npm install
npm run dev                                              # http://localhost:3000
```

#### Sign up flow

The org is auto-created from your email's domain (`alice@acme.com` → org
`acme`, you're stamped as `admin`). Subsequent users at the same domain
auto-join that org as `reviewer`. No invitations in v1; that's a deliberate
trade-off documented in
[`docs/superpowers/specs/2026-04-29-dashboard-design.md`](docs/superpowers/specs/2026-04-29-dashboard-design.md).

#### What you see on each page

- **`/runs`** — list of every run in your active org with status badges.
- **`/runs/new`** — drop in a JD text file plus 1+ resumes (PDF / DOCX / TXT
  / MD), choose `top_n` and `--skip-optional` if you want the cheaper run.
  The dashboard uploads each file to MinIO, creates a `runs` row with
  `status='queued'`, and the worker picks it up within `ATS_WORKER_POLL_S`
  seconds.
- **`/runs/[id]`** — live run detail:
  - **Job description card** — role / seniority / `min_years+ yrs` chips,
    must-have requirements as rose chips, nice-to-haves as blue chips,
    responsibilities as a bulleted list, plus a presigned-URL download
    of the original JD blob.
  - **Pipeline progress** — checklist of every orchestrator stage (JD
    analysis · parsing · dedup · scoring · red flags · interview Qs ·
    enrichment · bias · ranking · outreach) with a live count
    (`3 / 4 candidates`) and per-stage state (done / in-progress / pending
    / skipped). A collapsible recent-events log lists up to 50 audit rows.
  - **Bias audit** payload (when present).
  - **Candidate cards** — score, name, email, optional decision badge.
- **`/runs/[id]/candidates/[cid]`** — per-candidate detail:
  - **Summary panel** — score gauge (0–1 with markers), verdict badge
    (Strong / Mixed / Weak fit, derived from score; reviewer's manual
    decision overrides), pros (verifier-confirmed skills + strong GitHub
    signals), cons (hallucinated claims + red-flag entries), match
    rationale.
  - **Decision panel** — Shortlist / Hold / Reject + free-text notes.
    Persists to the new `decisions` table.
  - **Red flags** — gaps and overlaps as horizontal bar lists (months
    relative to the longest), inconsistencies as bullets.
  - **Interview questions** — numbered cards with skill chips and
    collapsible probe lists.
  - **GitHub enrichment** — stat tiles (repos / followers / top languages),
    notable-repos table with star and fork counts.
  - **Parsed resume** — contact card · skill chips · vertical experience
    timeline with bullets · education cards · clickable link chips.
  - **Comments thread** — per-candidate, with avatar initials and timestamps.
  - **Download resume** — presigned MinIO URL (5-minute expiry).

#### Architecture notes

Schema source-of-truth stays in Python ([`ats/storage/models.py`](ats/storage/models.py)).
The dashboard talks to Postgres directly via raw `pg` queries with
hand-typed TypeScript shapes in `dashboard/src/lib/types.ts` — no Prisma
migrations, no schema drift. Tenant isolation lives in
`dashboard/src/lib/repo.ts` (every query takes `orgId`) and is enforced at
the SQL level via composite foreign keys (`(org_id, id)`).

Auth is roll-our-own: bcrypt-hashed passwords + a server-side `sessions`
table; the cookie carries only the random session id. CSRF is handled by
`SameSite=Lax` plus an `Origin` header check on state-changing routes.

Flags:

```
ats screen --jd JD --resumes DIR
           [--top N]            shortlist size (default 5)
           [--skip-optional]    Needed + Recommended only (faster, cheaper)
           [--concurrency N]    override ATS_CONCURRENCY
           [--max-cost-usd X]   abort if total spend exceeds X
ats --log-level DEBUG --log-json screen ...
```

### Docker

```bash
docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v "$PWD/data:/data" \
  -v "$PWD/fixtures:/fixtures:ro" \
  ghcr.io/alirazmdideh/ats:latest \
  screen --jd /fixtures/jd.txt --resumes /fixtures/resumes/ --top 3
```

The image is non-root (uid 1000), uses `tini` as PID 1, and persists state at
`/data`.

---

## How it works

```
   Reviewer's browser
        │
        │ HTTPS (cookie session)
        ▼
   ┌────────────────────────────┐    ┌──────────────────────────────┐
   │   Next.js dashboard        │    │            MinIO              │
   │ - login / signup / sessions│    │ - orgs/<id>/jds/...           │
   │ - upload JD + resumes      │◄──►│ - orgs/<id>/resumes/<sha>/... │
   │ - decisions / comments     │    │ presigned GETs from dashboard │
   │ - reads from Postgres      │    └──────────────────────────────┘
   └─────────────┬──────────────┘                  ▲
                 │                                  │ resumes / JD
                 ▼                                  │ blob fetches
   ┌────────────────────────────┐                  │
   │         Postgres           │                  │
   │ orgs · users · memberships │                  │
   │ runs · candidates · scores │                  │
   │ shortlists · audits        │                  │
   │ sessions · decisions       │                  │
   │ candidate_comments         │                  │
   └─────────────┬──────────────┘                  │
                 │ FOR UPDATE SKIP LOCKED          │
                 ▼                                  │
   ┌────────────────────────────┐                  │
   │      ats worker (Python)    │──────────────────┘
   │  ┌── jd_analyzer            │
   │  │                          │
   │  parser ─► deduper ─► matcher ─► verifier ─► bias gate ─► ranker
   │           │           │           │
   │           └── red_flags / summarizer / interview_qs
   │           └── enricher (GitHub)
   │                                  │
   │                              shortlist
   │                                  │
   │                              outreach
   └────────────────────────────┘
```

`ats screen` (CLI) hits the same orchestrator without going through the queue;
the worker exists so the dashboard can hand-off long-running screening jobs.

| Tier | Agents |
|------|--------|
| **Needed** | parser, jd_analyzer, matcher, ranker |
| **Recommended** | verifier, bias_auditor, deduper |
| **Optional** | taxonomy, summarizer, red_flags, interview_qs, outreach, enricher |

`--skip-optional` runs Needed + Recommended only.

Every agent's output is validated against a Pydantic schema in
[`ats/agents/schemas.py`](ats/agents/schemas.py). Common shape mistakes (a list
where we expected an object, `{"data": ...}` wrappers) are coerced before
validation, so a slightly off-spec response from the model doesn't crash the
run.

---

## Quality gates

```bash
pytest -q                # unit + integration (offline, fake LLM)
mypy --strict ats
black --check ats tests
isort --check-only ats tests
flake8 ats tests
```

---

## Security

- The bundled `.env.example` is the only env file in the repo. `.env` is
  `.gitignore`'d. Do **not** commit it.
- API keys printed in chat or logs should be considered compromised. Rotate
  immediately at the provider's dashboard.
- The Docker image runs as a non-root user; mount your data volume read-write,
  fixture volume read-only.
- The `enricher` agent calls `https://api.github.com` and nothing else. The
  bias auditor never uses inferred demographic attributes for scoring — only
  for post-hoc disparity detection.
- Dashboard passwords are hashed with **bcrypt** (≥10 rounds). Sessions live
  server-side in the `sessions` table; the cookie carries only the random
  session id and is `HttpOnly; Secure; SameSite=Lax`. Logout sets
  `revoked_at`; reused / expired ids are rejected at the lookup layer.
- Resume + JD downloads from the dashboard go through **presigned MinIO
  URLs** with a 5-minute expiry. The cookie session never touches MinIO.
- Tenant isolation is enforced at three layers: composite SQL FKs
  (`(org_id, id)` parents, `(org_id, run_id)` children), the Python
  `OrgScopedRepository` base class, and the dashboard's `assertRunAndCandidateInOrg`
  guard on every mutation.

---

## Roadmap

Shipped:

- ✅ **Sub-project #1** — Postgres + MinIO + multi-tenant storage foundation
  (org-scoped repository layer, composite FKs for tenant isolation, async
  SQLAlchemy + aioboto3). Spec:
  [`docs/superpowers/specs/2026-04-29-storage-foundation-design.md`](docs/superpowers/specs/2026-04-29-storage-foundation-design.md)
  (or earlier `tell-me-what-cool-…` plan file).
- ✅ **Sub-projects #2–#4 (bundled)** — Next.js reviewer dashboard with
  email + password auth (bcrypt + server-side cookie sessions),
  upload-and-queue runs, live pipeline progress, JD card, candidate
  summary panel (score gauge / verdict / pros / cons), rich
  visualizations for red flags / interview questions / GitHub enrichment
  / parsed resume, decision panel, comment threads, presigned MinIO
  resume + JD downloads, dark theme with system-preference detection.
  Spec:
  [`docs/superpowers/specs/2026-04-29-dashboard-design.md`](docs/superpowers/specs/2026-04-29-dashboard-design.md).
- ✅ **Sub-project #5 (v1)** — append-only compliance log
  (`audit_log` table, distinct from agent `audits`). Reviewer + worker
  actions are recorded with actor / kind / target / payload + timestamp:
  `auth.login` / `auth.logout` / `auth.signup`,
  `run.submitted` / `run.started` / `run.completed` / `run.failed` /
  `run.budget_exceeded`,
  `decision.set`, `comment.added`. Admin-only viewer at
  `/settings/audit` with kind + date-range filters; CSV export at
  `/api/audit/export` streams the full filtered log for legal /
  compliance purposes (NYC AEDT, EU AI Act).
- ✅ **Sub-project #5b** — HMAC-chained tamper-evidence on `audit_log`.
  Each new row stores `prev_hash` + `hash` where
  `hash = HMAC-SHA256(secret, prev_hash || canonical_json(record))`.
  The same canonical-JSON contract is implemented in Python
  (`ats/storage/audit_chain.py`) and TypeScript
  (`dashboard/src/lib/audit-chain.ts`) so worker + dashboard writes
  chain into a single sequence per org. Per-org Postgres advisory
  locks (`pg_advisory_xact_lock(org_id)`) serialize concurrent
  writers. New endpoint `/api/audit/verify` walks the chain and
  reports the first break; the audit viewer has a "Verify chain"
  button that surfaces the result inline.

Deferred:
- ⏳ Password reset by email, email verification, multi-org invitations.
- ⏳ LinkedIn enricher (today the enricher is GitHub-only).
- ✅ **Real-time updates (SSE + Postgres LISTEN/NOTIFY)** — the run-detail
  page opens a single `EventSource` against `/api/runs/:id/stream`.
  Triggers on `runs` / `audits` / `scores` / `shortlists` emit
  `NOTIFY 'run_progress', '<run_id>'` after every relevant mutation; a
  Node-side singleton `pg.Client` stays subscribed and fans notifications
  out to every open SSE handler via an `EventEmitter`. So 100 open tabs
  share one PG connection, and updates land within a few ms of the
  worker writing — no client-side polling, no per-tab Postgres
  connection. A 5s server-side snapshot poll is kept as a safety net for
  any notification dropped during a reconnect window. 15s heartbeat
  comments keep the connection alive through corporate proxies.

---

## License

MIT — see [LICENSE](LICENSE).
