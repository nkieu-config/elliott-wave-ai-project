# Development & Deployment Guide

Everything you need to run, use, and test the project locally — and to put it in production.

> For the one-command Docker path, see [Quick Start in the README](../README.md#quick-start).

## Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running](#running)
- [Using the dashboard](#using-the-dashboard)
- [Calling the API directly](#calling-the-api-directly)
- [Testing](#testing)
- [Environment variables](#environment-variables)
- [Directory tree](#directory-tree)
- [Deploying: frontend (Vercel)](#deploying-frontend-vercel)
- [Deploying: backend (Render / Docker)](#deploying-backend-render--docker)
- [Scaling notes](#scaling-notes)
- [Security checklist](#security-checklist)

## Prerequisites

| Software                 | Version      | Notes                                                                                                      |
| ------------------------ | ------------ | ---------------------------------------------------------------------------------------------------------- |
| **Python**               | ≥ 3.11       | uv manages the version and environment for you                                                             |
| **uv**                   | ≥ 0.4        | Python package manager — see the [install guide](https://docs.astral.sh/uv/getting-started/installation/)  |
| **Node.js**              | ≥ 22         | Developed on v22; ships with npm (`package.json` engines pin ≥ 22)                                         |
| **Internet**             | Required     | For yfinance price data + Ollama Cloud                                                                     |
| **Ollama Cloud API key** | _(optional)_ | Needed only for the AI Analyst — [get a key](https://ollama.com/settings/keys)                             |

> [!NOTE]
> Without an Ollama Cloud API key the chart / KPI / scoring features work normally — only
> **AI Reading** and **Ask** need an LLM (or a local [Ollama](https://ollama.com) running the
> fallback model, to which the analyst fails over automatically). **Ask** also needs
> `ANALYST_QA=1` plus the `grounding` extra — see [Environment variables](#environment-variables).

## Installation

```bash
# 1) Clone the project
git clone https://github.com/nkieu-config/elliott-wave-ai-project.git
cd elliott-wave-ai-project

# 2) Install Python dependencies (uv creates .venv and installs from uv.lock)
uv sync --extra api

# 3) Install frontend dependencies
cd apps/web
npm install
cd ../..
```

## Configuration

```bash
# Copy the example file, then fill in your values
cp .env.example .env
```

Edit `.env` and add your Ollama Cloud API key:

```dotenv
OLLAMA_API_KEY=<your key from https://ollama.com/settings/keys>
```

The frontend calls `http://localhost:8000` by default, so no extra setup is needed for local
development. To point it at a different API, create `apps/web/.env.local` (git-ignored):

```dotenv
NEXT_PUBLIC_API_URL=https://your-api-host
```

## Running

Open two terminals:

```bash
# Terminal 1 — Backend (port 8000)
uv run uvicorn apps.api.main:app --reload --port 8000
```

```bash
# Terminal 2 — Frontend (port 3000)
cd apps/web
npm run dev
```

Then open your browser:

- **Dashboard:** <http://localhost:3000>
- **API docs (Swagger UI):** <http://localhost:8000/docs>

## Using the dashboard

1. Open <http://localhost:3000> — the app loads a default view (symbol `DDOG`, weekly, max range).
   The first load fetches live data from yfinance and caches it under `data/` automatically;
   subsequent loads read from the cache and appear instantly.
2. Choose a **symbol / period / timeframe** to fetch and re-analyze. Any symbol not yet cached is
   fetched live from yfinance.
3. The system ranks **wave-counting hypotheses (scenarios)** by a confidence score; inspect them
   one at a time and open a scenario to see its **score breakdown** (where the confidence comes
   from).
4. Toggle display layers (raw / trendline / latest) on the chart, then read the **AI Reading**
   panel, which streams a narration in real time (with theory citations) across four lenses:
   - **Structure** — what the current count is
   - **Outlook** — targets and the conditions that confirm them
   - **Risk** — the weakest link / invalidation
   - **Alternative** — the runner-up scenarios if this count is wrong
5. Press **`/`** or click **Ask** in the AI Reading header to ask a free-form Elliott Wave theory
   question — answered from the theory corpus with citations, optionally grounded in the selected
   scenario (requires `ANALYST_QA=1`).

## Calling the API directly

Everything the dashboard does is one of four POST routes. Interactive docs (dev only) live at
<http://localhost:8000/docs>; the shapes below are trimmed from real responses.

**Analyze a chart** — `POST /api/v1/pipeline`. Only `symbol` / `timeframe` / `period` are usually
needed; every detector and scoring knob has a default (see [`PipelineRequest`](../apps/api/schemas.py)).

```bash
curl -s -X POST http://localhost:8000/api/v1/pipeline \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"AAPL","timeframe":"day","period":"2y"}'
```

```jsonc
{
  "meta": { "symbol": "AAPL", "period": "2y", "timeframe": "day", "generated_at": "...", "config": { "...": "detector + scoring knobs echoed back" } },
  "scenario_counts": { "total": 52, "complete": 2, "open": 50 },
  "top_scenario": {
    "id": "e39ad2f685d0ec06",
    "score": 0.479,
    "family": "3W",
    "pattern_kind": "3W_NORMAL",
    "is_complete": true,
    "confidence_tier": { "key": "mid", "word": "Moderate" },
    "score_components": {
      "speed_cluster": 0.4795,          // ← structural weakest link, and the headline
      "fib_push_pairs": 0.9805,
      "pull_depth_discipline": 0.9653,
      "structural_total": 0.4795,
      "pivot_sharpness": 1.0,
      "leg_smoothness": 0.6589,
      "visual_total": 0.6589,
      "quality": 0.4795,                // = min(structural_total, visual_total)
      "commitment": 1.0,                // complete pattern — nothing left to close
      "total": 0.4795                   // = quality × commitment
    },
    "root": { "pattern_kind": "3W_NORMAL", "degree_label": "primary", "span_start": {}, "span_end": {}, "children": [] }
  },
  "top_scenario_layer1": { "bottleneck": {}, "confirmation": {}, "targets": {}, "decision": {}, "alternative": {}, "...": "deterministic diagnostics for the top scenario, computed eagerly to save a roundtrip" },
  "bars": [], "raw_pivots": [], "active_pivots": [], "selected_anchor": {}, "report": {}, "load_error": null
}
```

The full body also carries every bar, pivot, and all 52 scenarios (~380KB for this request) — the
chart draws from it without a second call. Score values shift as new bars arrive; see
[examples.md](examples.md) for the same chart walked through end to end.

**Layer-1 for any scenario** — `POST /api/v1/scenario/layer1`. The `/pipeline` response already
embeds the deterministic diagnostics for the top scenario; this returns the same block for any
other `scenario_id`, which is what the UI calls when you select a different count.

**Stream a narration** — `POST /api/v1/analyst/stream` (SSE). `mode` is the wire name of a lens:
`explanation` (Structure) / `outlook` / `risk` / `differentiator` (Alternative). Needs an
`OLLAMA_API_KEY`, or it falls back to deterministic Layer-1 text.

```bash
curl -sN -X POST http://localhost:8000/api/v1/analyst/stream \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"AAPL","timeframe":"day","period":"2y","mode":"risk","scenario_id":"e39ad2f685d0ec06"}'
```

```text
event: start
data: {"mode":"risk","model_id":"gpt-oss:120b","scenario_id":"e39ad2f685d0ec06"}

event: token
data: {"text":"The "}
...
event: citations
data: {"citations":[...],"cached":false,"fell_back":false,"model_id":"gpt-oss:120b","prompt_version":"..."}

event: done
data: {"total_tokens":...,"gen_ms":...}
```

Every number in those tokens (`$316.91`, `+0.5%`) is copied verbatim from the Layer-1 block in the
`/pipeline` response — that is what the grounding gate enforces.

**Theory Q&A** — `POST /api/v1/qa`, off unless `ANALYST_QA=1` and the `grounding` extra are
installed; answers `503` otherwise.

**Health** — `GET /api/health` → `{"status":"ok","service":"ewl-api"}` and `GET /api/ready` →
`{"status":"ready","analyst_prewarmed":true,"qa_enabled":false}`, which is how you confirm whether
Ask is actually enabled on a given deployment.

## Testing

```bash
# Python
uv sync --extra api --extra dev   # install the test toolchain (first time only)
uv run pytest -m "not slow"       # fast tests
uv run pytest                     # full suite

# Frontend
cd apps/web
npm test
```

CI runs the same checks on every push/PR — `ruff` + `pytest` (branch coverage ≥ 75%) on a
Python 3.11 + 3.12 matrix, and `tsc` + `eslint` + `next build` + `vitest` — see
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

## Environment variables

| Variable                    | Scope   | Default                 | Description                                                                                                          |
| --------------------------- | ------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `OLLAMA_API_KEY`            | analyst | _(required for AI)_     | Ollama Cloud API key                                                                                                 |
| `OLLAMA_PRIMARY_MODEL`      | analyst | `gpt-oss:120b`          | Primary model (cloud)                                                                                                |
| `OLLAMA_FALLBACK_MODEL`     | analyst | `qwen3.5:9b`            | Fallback model (local Ollama), used if the cloud call fails                                                          |
| `OLLAMA_CLOUD_CONCURRENCY`  | analyst | `1`                     | Cloud calls in flight at once. At `1`, the four narration lenses run one at a time — see the note below              |
| `ANALYST_QA`                | analyst | _(off)_                 | Set to `1` to enable the **Ask** theory Q&A (embedding retrieval; requires `uv sync --extra api --extra grounding`)  |
| `ANALYST_GROUNDING_CHECK`   | analyst | _(off)_                 | Set to `1` to enable the semantic grounding check (requires the `grounding` extra, pulls ~440MB torch)               |
| `EWL_API_CORS_ORIGINS`      | api     | _(dev regex)_           | Comma-separated allowlist of origins for production                                                                  |
| `EWL_ENV`                   | api     | _(unset)_               | Set to `production` to enforce CORS configuration and hide OpenAPI docs                                              |
| `EWL_DISABLE_FORCE_REFRESH` | api     | _(off)_                 | Set to `1` to disable force-refresh (prevents cache bypass that burns LLM calls on public deploys)                   |
| `EWL_CACHE_DIR`             | engine  | `<repo>/data`           | Directory for the price parquet cache                                                                                |
| `EWL_CACHE_MAX_BYTES`       | engine  | `268435456` (256MB)     | LRU budget for the parquet cache; over budget evicts oldest-fetched files first; `0` disables eviction               |
| `NEXT_PUBLIC_API_URL`       | web     | `http://localhost:8000` | API address the frontend calls                                                                                       |

Normally only `OLLAMA_API_KEY` (and `EWL_API_CORS_ORIGINS` when deploying) need setting; the rest
have working defaults. Finer knobs — Ollama timeouts / retries / concurrency, logging, Sentry
DSNs — also read from the environment; see
[`ollama_client.py`](../infra/llm/ollama_client.py),
[`logging_config.py`](../engine/logging_config.py), and `apps/web/sentry.*.config.ts`.

**On narration latency.** The dashboard requests all four AI Reading lenses at once, and
`OLLAMA_CLOUD_CONCURRENCY` decides whether the client actually issues them in parallel or queues them
behind a semaphore. The code default is `1` — the conservative choice, since a stricter API key can
answer parallel calls with rate-limit rejections, and those trip the failover path and degrade the
reading rather than just slowing it down. Raise it only once you have checked that your key tolerates
concurrent calls.

The hosted demo runs `OLLAMA_CLOUD_CONCURRENCY=4`. Measured cold (uncached NET weekly, four lenses
issued together against the deployed API):

| Setting                      | Wall time for all four lenses                    |
| ---------------------------- | ------------------------------------------------ |
| `OLLAMA_CLOUD_CONCURRENCY=1` | ~200s — four ~50s lenses, one after another      |
| `OLLAMA_CLOUD_CONCURRENCY=4` | **115s** — wall ≈ the slowest single lens (109s) |

The speedup is real but sub-linear, and the reason is worth knowing: under four concurrent requests
the per-lens generation time itself stretches (30s / 72s / 97s / 109s, against ~50s when a lens has
the model to itself), because Ollama Cloud's free tier shares throughput rather than capping
connections. Parallelism removes the queueing, not the contention. Each lens still streams the moment
it lands, and cached readings return immediately.

## Directory tree

```text
elliott-wave-ai-project/
├── README.md                     # Project overview (start here)
├── pyproject.toml                # Python package definition + dependencies (managed by uv)
├── uv.lock                       # Pinned dependency versions for reproducible installs
├── .env.example                  # Example configuration (copy to .env and fill in)
├── docker-compose.yml            # One-command full-stack run (api + web)
│
├── engine/                       # ── Symbolic core: rule-based Elliott Wave counter ──
│   ├── pivot.py                  #    Pivot detection (ATR-based ZigZag pivots)
│   ├── anchor.py                 #    Wave start selection (anchor)
│   ├── adaptive.py               #    Wave pattern families (3-wave / 5-wave trend / sideway)
│   ├── pipeline.py               #    Orchestration: pivots → anchor → wave counting
│   ├── parser/                   #    Beam-search wave counter + scoring
│   ├── verifiers/                #    Wave-rule checkers (trend / sideway / 3-wave / link)
│   ├── degree/                   #    Wave degree labeling (hierarchy)
│   └── data/                     #    BarSource / BarCache ports + repository (no vendor code)
│
├── analyst/                      # ── Neuro core: LLM-powered analyst ──
│   ├── orchestrator.py           #    Main coordinator (Analyst) + default singleton factory
│   ├── diagnostics/              #    Deterministic Layer-1: targets / bottlenecks / confirmation / decision / succession
│   ├── client/                   #    LLMClient port + response cache + grounding gate
│   ├── theory/                   #    Theory retrieval (RAG): chunker / embedder / retriever
│   │                             #    + corpus/ (the Elliott Wave theory source) and data/ (its embeddings)
│   ├── prompts/                  #    Prompt templates: 4 narration modes + theory Q&A + repair
│   └── schemas/ , serialization/ #    Result schemas + LLM input serialization
│
├── infra/                        # ── Adapters: the only code that talks to the outside world ──
│   ├── llm/                      #    OllamaClient — cloud primary + local failover
│   └── market_data/              #    YFinanceSource + ParquetCache (pandas confined here)
│
├── apps/
│   ├── api/                      # Backend: FastAPI — routers/ (pipeline, analyst, qa, health),
│   │                             #          services/, schemas.py, serializers.py, pipeline_ops.py
│   │                             #          + Dockerfile (image built from repo root)
│   └── web/                      # Frontend: Next.js 15 + React 19 (app/, components/, lib/)
│                                 #          + Dockerfile (multi-stage standalone build)
│
├── data/                         # Price cache (.parquet) — created automatically from yfinance
├── docs/                         # Architecture, examples, tradeoffs, and this guide
└── tests/                        # pytest suite (engine / analyst / infra / apps)
```

## Deploying: frontend (Vercel)

The system deploys as two separated services: **Vercel** for the Next.js frontend and **Render**
for the Python FastAPI backend.

> Live instance: [https://elliott-wave-web.vercel.app](https://elliott-wave-web.vercel.app)

- **Framework preset:** Next.js
- **Root directory:** `apps/web` — critical: must be set before deploying
- **Environment variables:**
  - `NEXT_PUBLIC_API_URL` = `https://<your-render-api-url>.onrender.com`

## Deploying: backend (Render / Docker)

Deploy the repository root (`.`) as a Docker Web Service, pointing to `apps/api/Dockerfile`.

- **Environment variables:**
  - `EWL_ENV=production` — enforces CORS configuration and hides OpenAPI docs
  - `EWL_API_CORS_ORIGINS=https://<your-vercel-frontend-url>.vercel.app`
  - `EWL_CACHE_DIR=/app/data/.cache` — points the caching engine at the writable volume in the
    Docker container
  - `OLLAMA_API_KEY=<your key>`
  - `OLLAMA_PRIMARY_MODEL` / `OLLAMA_FALLBACK_MODEL` — optional. Set either to swap models
    without rebuilding the image; leave them unset to take the defaults listed in the
    [environment-variable reference](#environment-variables). Ollama Cloud has retired a default
    model before, and this is the escape hatch when it happens again.
  - `OLLAMA_CLOUD_CONCURRENCY=4` — what the hosted demo runs, so the four narration lenses overlap
    instead of queueing (measured: 115s cold, against ~200s serialized — see the
    [latency note](#environment-variables)). Leave it unset to take the safe default of `1` unless
    you have confirmed your key tolerates parallel calls.

The API fails fast at startup if `EWL_ENV=production` is set without a CORS allowlist — the
permissive dev regex must never serve production traffic.

> [!WARNING]
> **Do not set `ANALYST_QA=1` on this image.** [`apps/api/Dockerfile`](../apps/api/Dockerfile)
> installs `--extra api` only, so `sentence-transformers` is absent and **Ask** cannot run. The
> service detects the missing extra at build time and disables the embedder, so `/api/v1/qa`
> answers `503` and `/api/ready` reports `qa_enabled: false` — but the flag is still a lie about
> intent. To actually serve Ask, add `--extra grounding` to both `uv sync` lines in the Dockerfile
> and give the instance enough memory for torch plus the 768-dim embedding model (~440MB of wheels
> and well over Render's free-tier 512MB RAM).

## Scaling notes

> [!IMPORTANT]
> **Run one worker per process.** In-process caches (price parquet cache, LLM response cache,
> wave-count memoization) aren't shared across workers, so `uvicorn --workers N` causes
> cross-worker cache misses. To scale horizontally, use a sticky-routing reverse proxy or move
> the caches to Redis.

Other cost/latency characteristics worth knowing:

- LLM narrations are cached on disk with content-derived keys, so repeat views of the same
  scenario are free and stream instantly (the UI shows cached playback without a fake typewriter).
- Price data has per-timeframe TTLs (day 12h / week 1d / month 3d), so yfinance is only hit when
  a bar could actually have changed.

## Security checklist

> [!WARNING]
> Endpoints have **no app-level auth and no rate limiting** — the live deployment relies on CORS,
> the force-refresh guard, and caching to bound cost. For anything beyond a demo:

- Set `EWL_API_CORS_ORIGINS` to the exact frontend origin(s).
- Set `EWL_DISABLE_FORCE_REFRESH=1` to block the cache bypass that lets clients burn unbounded
  LLM calls.
- Keep `EWL_ENV=production` so OpenAPI docs stay hidden and misconfigured CORS fails at startup.
- Put a rate limiter (or an auth proxy) in front of the API before exposing it beyond a portfolio
  demo audience.
