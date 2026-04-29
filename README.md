# ATS — AI-Powered Resume Screening

[![CI](https://github.com/aliRazmdideh/ats/actions/workflows/ci.yml/badge.svg)](https://github.com/aliRazmdideh/ats/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ats-screen.svg)](https://pypi.org/project/ats-screen/)
[![Python](https://img.shields.io/pypi/pyversions/ats-screen.svg)](https://pypi.org/project/ats-screen/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A multi-agent CLI for screening resumes against a job description. Built on the
[Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/python). Runs against
the native Anthropic API or any compatible endpoint (OpenRouter is the tested
alternative).

13 cooperating subagents — parser, jd_analyzer, matcher, ranker, verifier,
bias_auditor, deduper, taxonomy, summarizer, red_flags, interview_qs, outreach,
enricher — orchestrated through one `ClaudeSDKClient` with bounded concurrency,
structured logging, retry-with-backoff, schema validation on every output, and
per-run USD cost accounting.

Persists to **Postgres** (results, audits, candidates, runs, orgs / users /
memberships) and **MinIO** (resume + JD blobs) behind an org-scoped
repository layer — multi-tenant from day one.

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

A Next.js reviewer dashboard lives in [`dashboard/`](dashboard/) — multi-tenant signup / login, JD + resume uploads that queue runs for the worker, and a per-candidate UI for shortlist / hold / reject decisions plus a comment thread.

```bash
make dev-up                    # Postgres + MinIO
ats init                       # schema + bucket
ats worker &                   # background worker that processes queued runs
cd dashboard
cp .env.example .env.local
npm install
npm run dev                    # http://localhost:3000
```

Sign up at `/signup` — the org is auto-created from your email's domain (`alice@acme.com` → `acme`). Subsequent users at the same domain auto-join that org as `reviewer`. Schema source-of-truth stays in Python (`ats/storage/models.py`); the dashboard reads/writes via raw `pg` queries with hand-typed TypeScript shapes.

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
                 ┌── jd_analyzer
                 │
resumes ─► parser ─► deduper ─► matcher ─► verifier ─► bias gate ─► ranker
                                  │           │            │
                                  └── red_flags / summarizer / interview_qs
                                  └── enricher (GitHub)
                                                              │
                                                          shortlist
                                                              │
                                                           outreach
```

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

---

## Roadmap

- ✅ Sub-project #1: Postgres + MinIO + multi-tenant storage foundation.
- ✅ Sub-projects #2–#4 (bundled): Next.js reviewer dashboard with email +
  password auth (cookie sessions), upload-and-queue runs, per-candidate
  shortlist / hold / reject decisions, comment threads, presigned MinIO
  resume downloads.
- ⏳ Sub-project #5: append-only signed audit log + compliance export.
- ⏳ Password reset by email, email verification, multi-org invitations.
- ⏳ LinkedIn enricher (today the enricher is GitHub-only).

---

## License

MIT — see [LICENSE](LICENSE).
