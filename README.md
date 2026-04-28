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
| `ATS_DB_PATH` | `./ats.db` | SQLite database path |
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

```bash
ats init
ats screen --jd path/to/jd.txt --resumes path/to/resumes/ --top 5
ats report --run 1 --cost
ats outreach --run 1 --decision shortlist
```

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

Out of scope for v1.0 but on the radar:

- HTTP / FastAPI service for batch ingest.
- Postgres + S3 backend.
- LinkedIn enricher (today the enricher is GitHub-only).
- Multi-tenant auth.

---

## License

MIT — see [LICENSE](LICENSE).
