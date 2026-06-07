# fintech-fraud-mcp

A Python MCP (Model Context Protocol) server that connects Claude to a PostgreSQL transactions database and detects fraud patterns using SQL. Built with production-grade error handling, observability, security, and one-command deployment.

## What is MCP?

MCP is an open standard that lets AI models like Claude connect to external tools and data sources. Instead of Claude guessing about your data, it calls real functions — here, SQL queries against a live database — and reasons over actual results.

This server exposes 9 tools to Claude over **HTTP/SSE transport**. SSE (Server-Sent Events) means Claude connects to a running HTTP server rather than a subprocess, which is the correct transport for multi-user or networked deployments.

## Fraud patterns detected

| Tool | What it finds |
|------|---------------|
| `detect_duplicate_transactions` | Same user, same merchant, same amount within N seconds — double charges or replay attacks |
| `detect_location_anomalies` | User transacts in an Indian city then abroad within 30 minutes — impossible travel, likely stolen card |
| `detect_late_night_large_transactions` | Transactions between 2–4 AM that are 3x+ the user's average spend — account takeover signal |
| `detect_rapid_fire_transactions` | 5+ transactions within 90 seconds — bot activity or card testing |
| `get_fraud_summary` | Reads a pre-computed materialized view — instant report, no heavy queries at call time |
| `refresh_fraud_summary` | Re-runs all 4 detectors in the background and updates the materialized view |
| `get_user_profile` | Full spending profile for a user — cached for 5 minutes, use before making any fraud judgment |
| `get_schema` | Returns the transactions table schema |
| `query_transactions` | Ad-hoc read-only SQL — runs as a restricted `fraud_reader` user with SELECT-only access |

## Prerequisites

- Docker (for the self-contained dev stack — no local postgres needed)
- Python 3.11+ and PostgreSQL 16 (only if running without Docker)
- Claude Code CLI

## Quick start — Docker (recommended)

Zero dependencies beyond Docker. Postgres, migrations, and seed data are all included.

```bash
# 1. Clone and enter the project
git clone https://github.com/abhiparashar/fintech-fraud-mcp
cd fintech-fraud-mcp

# 2. Configure environment
cp .env.example .env       # defaults work out of the box for dev

# 3. Start the full stack (app + postgres, auto-migrated + seeded)
make dev-up-d

# 4. Verify it's running
make health
# {"status": "healthy", "db": "connected"}

# 5. Register with Claude Code and connect
make mcp-add
claude
```

The first `make dev-up-d` builds the image and runs all migrations automatically. Subsequent starts reuse the existing data volume. To reset to a clean slate:

```bash
make dev-reset    # wipes the DB volume and re-seeds everything fresh
```

## Quick start — local (no Docker)

```bash
# 1. Clone and enter the project
git clone https://github.com/abhiparashar/fintech-fraud-mcp
cd fintech-fraud-mcp

# 2. Install dependencies
make install

# 3. Configure environment
cp .env.example .env
# Edit .env — set DB_PASSWORD at minimum

# 4. Start PostgreSQL and create the database
brew services start postgresql@16
psql -U postgres -c "CREATE DATABASE fintechdb;" 2>/dev/null || true

# 5. Run migrations
make migrate

# 6. Start the server
make run

# 7. Register with Claude Code and connect
make mcp-add
claude
```

## Makefile — all commands

Run `make help` to see the full list. Key commands:

```bash
# Local dev
make install       # create .venv + install dependencies
make migrate       # run all DB migrations
make run           # start server locally (HTTP, port 8000)
make test          # run manual test suite

# Health & observability
make health        # curl /health with formatted output
make metrics       # curl /metrics (Prometheus)

# Docker dev stack (app + bundled postgres, seed data included)
make dev-up        # start app + postgres (foreground)
make dev-up-d      # start app + postgres (background)
make dev-down      # stop
make dev-logs      # tail logs
make dev-reset     # wipe DB volume and restart fresh

# Docker app-only (external DB, HTTP)
make build         # build Docker image
make up            # start with Docker Compose (foreground)
make up-d          # start with Docker Compose (background)
make down          # stop
make logs          # tail container logs

# Production (HTTPS via Caddy)
make prod-up       # start app + Caddy with auto TLS
make prod-down     # stop production stack
make prod-logs     # tail production logs

# Claude Code
make mcp-add                            # register local server
make mcp-add-prod DOMAIN=your.domain    # register production server
make mcp-list                           # list registered MCP servers

# Cleanup
make clean         # remove .venv and cache files
```

## Environment variables

Copy `.env.example` to `.env` and fill in your values. Never commit `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `fintechdb` | Database name |
| `DB_USER` | `postgres` | Main DB user |
| `DB_PASSWORD` | `password` | Main DB user password |
| `DB_READONLY_USER` | `fraud_reader` | Read-only user for `query_transactions` |
| `DB_READONLY_PASSWORD` | `readonly_password` | Read-only user password |
| `MCP_API_KEY` | *(unset)* | When set, enforces `X-API-Key` auth on the SSE endpoint |

## Running the server

**Dev stack — app + postgres bundled (recommended):**
```bash
make dev-up-d
# server at http://localhost:8000
# postgres at localhost:5433
```

**Local (no Docker):**
```bash
make run
# server at http://localhost:8000
```

**App only — Docker with external DB:**
```bash
make build
make up-d
# server at http://localhost:8000
```

**Production (Docker + HTTPS):**
```bash
# 1. Edit Caddyfile — replace fraud.yourdomain.com with your domain
# 2. Point your domain's DNS A record to the server IP
# 3. Fill in .env
make prod-up
# server at https://your.domain — TLS cert fetched automatically
```

## Connecting to Claude Code

**Local:**
```bash
make mcp-add
# or manually:
claude mcp add --transport sse fintech-fraud http://localhost:8000/sse
```

**Production:**
```bash
make mcp-add-prod DOMAIN=fraud.yourdomain.com
```

If `MCP_API_KEY` is set, add the header to `~/.claude.json`:

```json
{
  "mcpServers": {
    "fintech-fraud": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": { "X-API-Key": "yoursecretkey" }
    }
  }
}
```

Then ask Claude things like:

- *"Run get_fraud_summary"*
- *"Get the profile for user 10"*
- *"Detect location anomalies with a 20-minute window"*
- *"Which users appear in multiple fraud patterns?"*
- *"Refresh the fraud summary then show me the results"*

## Monitoring

### Health check

```bash
make health
# {"status": "healthy", "db": "connected"}
# Returns 503 if the database is unreachable
```

### Prometheus metrics

```bash
make metrics
```

| Metric | Type | Description |
|--------|------|-------------|
| `mcp_tool_calls_total` | Counter | Calls per tool, labelled by `tool` and `status` (success/error) |
| `mcp_tool_duration_seconds` | Histogram | Latency per tool with P50/P95/P99 buckets |
| `db_pool_connections_in_use` | Gauge | Connections currently checked out from the main pool |
| `db_pool_connections_available` | Gauge | Idle connections in the main pool |
| `mcp_profile_cache_hits_total` | Counter | `get_user_profile` calls served from cache |
| `mcp_profile_cache_misses_total` | Counter | `get_user_profile` calls that hit the database |

### Structured logs

Every log line is JSON with a `trace_id` field. All log entries for a single Claude tool call share the same trace ID:

```json
{"time": "2026-06-07T10:00:01", "level": "INFO", "trace_id": "a3f9c1b2d4e8", "message": "tool=get_fraud_summary trace=a3f9c1b2d4e8 started"}
{"time": "2026-06-07T10:00:01", "level": "INFO", "trace_id": "a3f9c1b2d4e8", "message": "tool=get_fraud_summary trace=a3f9c1b2d4e8 finished duration=0.043s status=success"}
```

## Project structure

```
src/
  server.py    — Entry point: logging setup, auth middleware, health/metrics routes, uvicorn
  app.py       — FastMCP singleton (avoids circular imports)
  db.py        — Two connection pools (main + readonly), retry logic, handle_db_errors decorator
  tools.py     — All 9 @mcp.tool() definitions
  tracing.py   — ContextVar trace ID: new ID per tool call, flows through the call stack
  metrics.py   — Prometheus counters, histograms, and gauges

migrations/
  001_fraud_summary_mv.sql  — fraud_user_flags materialized view + unique index
  002_readonly_user.sql     — fraud_reader user with SELECT-only access

Dockerfile              — Production image (non-root user, healthcheck)
docker-compose.dev.yml  — Dev stack: app + postgres with seed data (self-contained)
docker-compose.yml      — App only (external DB, HTTP)
docker-compose.prod.yml — Production: app + Caddy HTTPS
Caddyfile               — Caddy reverse proxy config (auto TLS via Let's Encrypt)
Makefile                — All commands in one place
.env.example            — Environment variable template
DEMO.md                 — CTO demo runbook with presentation order and test suite
```

## Architecture decisions

**Connection pooling** — `ThreadedConnectionPool(min=2, max=20)` shared across all threads. Opening a new socket per request would exhaust PostgreSQL's connection limit under concurrent load.

**Two pools** — the main pool (`postgres` user) runs fraud detection queries; a separate readonly pool (`fraud_reader`) runs `query_transactions`. A restricted user limits blast radius if arbitrary SQL is passed.

**Retry with exponential backoff** — Tenacity retries transient `OperationalError` and `PoolError` up to 3 times with exponential backoff (1s, 2s). Transient DB blips are invisible to the user.

**Materialized view for `get_fraud_summary`** — the four fraud detectors are heavy self-joins. Instead of running them on every call, `refresh_fraud_summary` pre-computes results into `fraud_user_flags`. `get_fraud_summary` then reads pre-computed rows — instant regardless of table size.

**TTLCache for `get_user_profile`** — user spending profiles change infrequently. A 5-minute in-process cache (max 500 users, thread-safe via RLock) eliminates repeated DB queries for cached users.

**Trace IDs** — Python's `contextvars.ContextVar` binds a new 12-character trace ID at the start of every tool call. The JSON formatter reads it on every log line, so all log entries for one Claude invocation are correlated without passing the ID through every function.

**Auth middleware** — `APIKeyMiddleware` (Starlette `BaseHTTPMiddleware`) checks `X-API-Key` on all routes except `/health` and `/metrics`. Enforcement is a no-op when `MCP_API_KEY` is unset, so local development requires no configuration change.

**HTTPS via Caddy** — Caddy sits in front of uvicorn as a reverse proxy. It automatically obtains and renews TLS certificates from Let's Encrypt. No manual cert management.

**Explicit Starlette routing** — `/health` and `/metrics` are registered as named `Route` entries in a top-level Starlette app, with the MCP SSE app mounted at `/` as a catch-all. This is version-agnostic and does not depend on FastMCP internals.

## Database schema

```
transactions
  id          | integer
  user_id     | integer
  merchant    | text
  amount      | numeric
  category    | text
  location    | text
  ip_address  | text
  txn_date    | timestamp

fraud_user_flags  (materialized view)
  user_id     | integer
  pattern     | text      — duplicate_charges | impossible_location | late_night_large_spend | rapid_fire
```

## Tech stack

| Library | Purpose |
|---------|---------|
| **FastMCP** | Python SDK for the Model Context Protocol |
| **Uvicorn** | ASGI server that runs the SSE endpoint |
| **Starlette** | Web framework: middleware, custom routes, SSE transport |
| **psycopg2** | PostgreSQL driver with `ThreadedConnectionPool` |
| **cachetools** | `TTLCache` with LRU eviction for user profiles |
| **tenacity** | Retry with exponential backoff for transient DB errors |
| **prometheus_client** | Metrics exposition at `/metrics` |
| **Caddy** | Reverse proxy with automatic TLS (production) |
| **Docker** | Containerised deployment |
