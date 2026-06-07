# CTO Demo Runbook — fintech-fraud-mcp

---

## Presentation order

Think of it as four acts. Each one answers a question the CTO is silently asking.

| Act | Duration | What you show | What they hear |
|-----|----------|---------------|----------------|
| 1 — The Problem | 2 min | Raw transactions table | "This is a real problem" |
| 2 — It Works | 3 min | Claude detecting fraud live | "This actually works" |
| 3 — Production Grade | 4 min | Health, metrics, logs, auth, errors | "This is production ready" |
| 4 — Easy to Ship | 2 min | Makefile + Docker + HTTPS | "We can deploy this" |

**Total: ~11 minutes. Leave 5 minutes for questions.**

> Golden rule: show the value before showing the code. Acts 1 and 2 happen before any file is opened.

---

## Night before — setup (do this at home)

```bash
cp .env.example .env
make dev-up-d          # builds image, starts app + postgres, runs migrations, seeds DB
make health            # confirm: {"status": "healthy", "db": "connected"}
make mcp-add           # register server with Claude Code (one-time)
make dev-down          # stop — you'll restart fresh on the day
```

That's all the setup. On demo day just run `make dev-up-d` and everything is ready.

---

## Demo day — exact commands in order

Open **two terminal windows** side by side before the CTO walks in.

```
Terminal A  →  server logs (keep visible throughout)
Terminal B  →  commands you run live
```

**Terminal A — start everything:**
```bash
make dev-up-d          # starts app + postgres in background
make dev-logs          # stream logs so CTO can see them live
```

**Terminal B — confirm it's up:**
```bash
make health
# {"status": "healthy", "db": "connected"}
```

---

## Act 1 — The Problem (2 min)

> "We have thousands of transactions. Finding fraud manually is impossible."

**Terminal B:**
```bash
psql -h localhost -p 5433 -U postgres -d fintechdb \
  -c "SELECT COUNT(*) FROM transactions;"

psql -h localhost -p 5433 -U postgres -d fintechdb \
  -c "SELECT * FROM transactions LIMIT 5;"
```

Say: *"A human analyst would need hours to run the right queries across all these records. I've built an AI-powered fraud detection system where Claude does this analysis in seconds — connected to the live database."*

---

## Act 2 — It Works (3 min)

**Terminal B — open Claude Code:**
```bash
claude
```

Expected — JSON logs, server ready:
```
{"time": "...", "level": "INFO", "message": "Uvicorn running on http://0.0.0.0:8000"}
```

Verify connection inside Claude:
```
/mcp
```
Expected: `fintech-fraud` listed as connected.

**Now run these in Claude, in this order:**

```
Run get_fraud_summary
```
→ Instant fraud report. Say: *"This reads a pre-computed view — always instant, no heavy queries at call time."*

```
Get the profile for user 10
```
→ Full spending profile. Say: *"Claude now understands what's normal for this user before making any fraud judgment."*

```
Get the profile for user 10 again
```
→ Point at Terminal A: `duration=0.000s`. Say: *"Second call is instant — served from in-memory cache. No DB hit."*

```
Which users appear in more than one fraud pattern?
```
→ Say: *"This is the power — Claude doesn't just query, it reasons over the results."*

---

## Act 3 — Production Grade (4 min)

Switch to Terminal B for each of these.

### Health check
```bash
make health
```
```json
{"status": "healthy", "db": "connected"}
```
*"One endpoint any monitoring system can ping. Returns 503 if the DB is down."*

### Prometheus metrics
```bash
make metrics
```
Point at these lines:
```
db_pool_connections_available 2.0     ← pool live, 2 idle connections ready
mcp_tool_calls_total{...}             ← per-tool call counter
mcp_tool_duration_seconds_sum{...}    ← latency histogram
mcp_profile_cache_hits_total 2.0      ← cache working
```
*"Plug in Grafana and you have dashboards and alerts in 10 minutes."*

### Structured logs with trace IDs
Point at Terminal A. Show a log line:
```json
{"trace_id": "a3f9c1b2d4e8", "message": "tool=get_user_profile finished duration=0.048s status=success"}
```
*"Every log line is JSON with a trace ID. All lines for one Claude call share the same ID — filter by it in any log aggregator to see exactly what happened."*

### API key auth
Restart stack with auth enabled — Ctrl+C in Terminal A, then:
```bash
export MCP_API_KEY=demosecret
make dev-up-d
make dev-logs
```

```bash
# No key — blocked
curl -s http://localhost:8000/sse
```
```json
{"error": "Unauthorized"}
```

```bash
# Health exempt — always open
curl -s http://localhost:8000/health
```
```json
{"status": "healthy", "db": "connected"}
```

```bash
# Correct key — SSE stream opens
curl -s -H "X-API-Key: demosecret" http://localhost:8000/sse
```
```
event: endpoint
data: /messages/?session_id=...
```
*"API key enforcement on the SSE endpoint. Health and metrics are exempt so monitoring always works."*

Restore for remaining steps:
```bash
make dev-down
unset MCP_API_KEY
make dev-up-d
make dev-logs
```

### Error handling — DB down
Stop just the DB container, leave the app running:
```bash
docker stop fintech-fraud-mcp-db-1
make health
```
```json
{"status": "unhealthy", "db": "..."}
```

Watch Terminal A — tenacity retries fire:
```
DB connection attempt 1 failed, retrying...
DB connection attempt 2 failed, retrying...
```

Call a tool from Claude — show the clean message, not a stack trace:
```
Get the profile for user 10
```
→ *"Database temporarily unavailable. Please try again in a moment."*

*"Users see a clean message. The real error with the trace ID is in the logs."*

Restore:
```bash
docker start fintech-fraud-mcp-db-1
make health
# {"status": "healthy", "db": "connected"}
```

### Query safety
```bash
make test
```
```
✓  'SELECT pg_sleep(100)'
   → Error: query contains a blocked keyword...
✓  'SELECT pg_read_file("/etc")'
   → Error: query contains a blocked keyword...
✓  'INSERT INTO transactions'
   → Error: only SELECT queries are allowed.
✓  'DROP TABLE transactions'
   → Error: only SELECT queries are allowed.
```
Point at Terminal A: `duration=0.000s`. *"Checks fire before any DB call — zero DB load, instant rejection."*

### TTL cache proof
```bash
make test
```
```
Call 1 (cold) — duration=0.048s   misses: 1   hits: 0
Call 2 (warm) — duration=0.000s   misses: 1   hits: 1
Call 3 (warm) — duration=0.000s   misses: 1   hits: 2

✓  1 miss + 2 hits recorded correctly
```
*"48ms on the first call, 0ms on every call after — in-memory cache, no DB."*

---

## Act 4 — Easy to Ship (2 min)

### All commands in one place
```bash
make help
```
*"One command for everything — no need to remember docker compose flags or curl options."*

### What they just saw running
```bash
make dev-up-d      # started everything — app + postgres + migrations + seed data
make dev-logs      # live JSON logs with trace IDs
make health        # health check
make metrics       # Prometheus metrics
make test          # automated test suite
make dev-down      # tear it all down
```

### Production with HTTPS — two steps
```bash
# 1. Edit Caddyfile — replace fraud.yourdomain.com with your domain
# 2. Run:
make prod-up
```
*"Caddy automatically fetches a TLS certificate from Let's Encrypt. HTTPS in one command — no manual cert management."*

### Connect Claude to production
```bash
make mcp-add-prod DOMAIN=fraud.yourdomain.com
```

### Connect Claude to production
```bash
make mcp-add-prod DOMAIN=fraud.yourdomain.com
```

---

## Full technical test suite (reference)

These are the detailed step-by-step tests with exact expected outputs.

### 1. Health check

```bash
make health
```
```json
{"status": "healthy", "db": "connected"}
```

Simulate DB failure:
```bash
docker stop fintech-fraud-mcp-db-1
make health
# {"status": "unhealthy", "db": "..."}  — 503
docker start fintech-fraud-mcp-db-1
make health
# {"status": "healthy", "db": "connected"}
```

### 2. Prometheus metrics

```bash
make metrics
```

Key metrics to check:
```
db_pool_connections_available 2.0     ← pool live (minconn=2)
mcp_profile_cache_hits_total 0.0      ← no tool calls yet
mcp_tool_calls_total                  ← empty until tools are called
```

### 3. Auth middleware

```bash
export MCP_API_KEY=testsecret
make dev-down && make dev-up-d        # restart with auth

curl -s http://localhost:8000/sse                              # → 401
curl -s http://localhost:8000/health                           # → 200 (exempt)
curl -s -H "X-API-Key: testsecret" http://localhost:8000/sse  # → SSE stream

make dev-down
unset MCP_API_KEY
make dev-up-d                         # restore
```

### 4. Query safety

```bash
make test
```

Expected:
```
✓  'SELECT pg_sleep(100)'      → blocked keyword
✓  'SELECT pg_read_file("/etc")' → blocked keyword
✓  'INSERT INTO transactions'  → only SELECT allowed
✓  'DROP TABLE transactions'   → only SELECT allowed
```

### 5. TTLCache

```bash
make test
```

Expected:
```
Call 1 (cold) — duration=0.048s   misses: 1   hits: 0
Call 2 (warm) — duration=0.000s   misses: 1   hits: 1
Call 3 (warm) — duration=0.000s   misses: 1   hits: 2
✓  1 miss + 2 hits recorded correctly
```

### 6. Metrics after tool calls

```bash
make metrics | grep mcp_tool
```

```
mcp_tool_calls_total{tool="get_user_profile",status="success"} 3.0
mcp_tool_duration_seconds_sum{tool="get_user_profile"} 0.048
mcp_profile_cache_hits_total 2.0
mcp_profile_cache_misses_total 1.0
```

### 7. Claude live tool calls

```bash
make dev-up-d   # if not already running
make mcp-add    # register (one-time)
claude
```

In Claude:
```
Run get_fraud_summary
Get the profile for user 10
Get the profile for user 10 again      ← watch Terminal A: duration=0.000s
Detect location anomalies with a 20-minute window
Call refresh_fraud_summary             ← returns immediately
Which users appear in more than one fraud pattern?
```

Watch Terminal A after `refresh_fraud_summary`:
```json
{"message": "fraud_user_flags refresh completed"}
```

### 8. Trace ID correlation

In Terminal A, every tool call logs a start and end line sharing the same `trace_id`:

```json
{"trace_id": "a3f9c1b2d4e8", "message": "tool=get_fraud_summary started"}
{"trace_id": "a3f9c1b2d4e8", "message": "tool=get_fraud_summary finished duration=0.043s status=success"}
```

---

## What this demo covers

| Capability | How shown |
|------------|-----------|
| Connection pooling | `db_pool_connections_available` gauge in `/metrics` |
| Retry on DB failure | `brew services stop` → retry logs → clean error message |
| Structured logging | JSON lines with `trace_id` in Terminal A |
| Prometheus metrics | `/metrics` before and after tool calls |
| API key auth | 401 without key, 200 with key, health always exempt |
| Query safety | Blocked keywords + SELECT-only guard, `duration=0.000s` |
| In-memory cache | 48ms cold → 0ms warm, counters in `/metrics` |
| Materialized view | `get_fraud_summary` instant, `refresh_fraud_summary` background |
| Background threads | Refresh returns immediately, completion logged seconds later |
| MCP + Claude | Live fraud detection reasoning over real DB data |
| Docker | `make build && make up-d` |
| HTTPS | `make prod-up` — Caddy auto TLS |
