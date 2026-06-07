# fintech-fraud-mcp

A Python MCP (Model Context Protocol) server that connects Claude to a PostgreSQL transactions database and detects fraud patterns using SQL. Built with production-grade error handling, observability, and security.

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

- Python 3.11+
- PostgreSQL 16 (`brew install postgresql@16`)
- Claude Code CLI

## Setup

```bash
# 1. Clone and enter the project
git clone https://github.com/abhiparashar/fintech-fraud-mcp
cd fintech-fraud-mcp

# 2. Create a virtual environment with Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start PostgreSQL and create the database
brew services start postgresql@16
psql -U postgres -c "CREATE DATABASE fintechdb;" 2>/dev/null || true

# 5. Run migrations
psql -U postgres -d fintechdb -f migrations/001_fraud_summary_mv.sql
psql -U postgres -d fintechdb -f migrations/002_readonly_user.sql
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PASSWORD` | `password` | Main DB user password |
| `DB_READONLY_USER` | `fraud_reader` | Read-only user for `query_transactions` |
| `DB_READONLY_PASSWORD` | `readonly_password` | Read-only user password |
| `MCP_API_KEY` | *(unset)* | When set, enforces `X-API-Key` auth on the SSE endpoint |

Set them before starting the server:

```bash
export DB_PASSWORD=yourpassword
export MCP_API_KEY=yoursecretkey   # optional — enables SSE auth
```

## Running the server

```bash
.venv/bin/python3 src/server.py --sse
```

The server starts on `http://localhost:8000`. Logs are emitted as structured JSON to stdout.

## Connecting to Claude Code

Register the server once:

```bash
claude mcp add --transport sse fintech-fraud-mcp http://localhost:8000/sse
```

If `MCP_API_KEY` is set, add the header to `~/.claude.json`:

```json
{
  "mcpServers": {
    "fintech-fraud-mcp": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": { "X-API-Key": "yoursecretkey" }
    }
  }
}
```

Then start the server and open Claude Code. Ask things like:

- *"Run get_fraud_summary"*
- *"Get the profile for user 10"*
- *"Detect location anomalies with a 20-minute window"*
- *"Which users appear in multiple fraud patterns?"*
- *"Refresh the fraud summary then show me the results"*

## Monitoring

### Health check

```bash
curl http://localhost:8000/health
# {"status": "healthy", "db": "connected"}
# Returns 503 if the database is unreachable
```

### Prometheus metrics

```bash
curl http://localhost:8000/metrics
```

Exposes:

| Metric | Type | Description |
|--------|------|-------------|
| `mcp_tool_calls_total` | Counter | Calls per tool, labelled by `tool` and `status` (success/error) |
| `mcp_tool_duration_seconds` | Histogram | Latency per tool with P50/P95/P99 buckets |
| `db_pool_connections_in_use` | Gauge | Connections currently checked out from the main pool |
| `db_pool_connections_available` | Gauge | Idle connections in the main pool |
| `mcp_profile_cache_hits_total` | Counter | `get_user_profile` calls served from cache |
| `mcp_profile_cache_misses_total` | Counter | `get_user_profile` calls that hit the database |

### Structured logs

Every log line is JSON with a `trace_id` field. All log entries for a single Claude tool call share the same trace ID, so you can correlate exactly what happened during one invocation:

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
```

## Architecture decisions

**Connection pooling** — `ThreadedConnectionPool(min=2, max=20)` shared across all threads. Opening a new socket per request would exhaust PostgreSQL's connection limit under concurrent load.

**Two pools** — the main pool (postgres user) runs fraud detection queries; a separate readonly pool (fraud_reader) runs `query_transactions`. A restricted user limits blast radius if arbitrary SQL is passed.

**Materialized view for `get_fraud_summary`** — the four fraud detectors are heavy self-joins. Instead of running them on every call, `refresh_fraud_summary` pre-computes results into `fraud_user_flags`. `get_fraud_summary` then reads 11 pre-computed rows — instant regardless of table size.

**TTLCache for `get_user_profile`** — user spending profiles change infrequently. A 5-minute in-process cache (max 500 users, thread-safe via RLock) eliminates 4 SQL queries per fraud investigation for cached users.

**Trace IDs** — Python's `contextvars.ContextVar` binds a new 12-character trace ID at the start of every tool call. The JSON formatter reads it on every log line, so all log entries for one Claude invocation are correlated without passing the ID through every function.

**Auth middleware** — `APIKeyMiddleware` (Starlette `BaseHTTPMiddleware`) checks `X-API-Key` on all routes except `/health` and `/metrics`. Enforcement is a no-op when `MCP_API_KEY` is unset, so local development requires no configuration change.

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

- **FastMCP** — Python SDK for the Model Context Protocol
- **Uvicorn** — ASGI server that runs the SSE endpoint
- **Starlette** — Web framework: middleware, custom routes, SSE transport
- **psycopg2** — PostgreSQL driver with `ThreadedConnectionPool`
- **cachetools** — `TTLCache` with LRU eviction for user profiles
- **tenacity** — Retry with exponential backoff for transient DB errors
- **prometheus_client** — Metrics exposition at `/metrics`
