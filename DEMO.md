# CTO Demo Runbook — fintech-fraud-mcp

Walk through each section in order. Expected output is shown under every command.

---

## 0. Prerequisites

```bash
# PostgreSQL running
brew services list | grep postgresql
# postgresql@16  started

# Virtual environment exists
ls .venv/bin/python3
# .venv/bin/python3
```

---

## 1. Start the server

**Terminal A — keep this open throughout the demo:**
```bash
cd ~/Desktop/fintech-fraud-mcp
.venv/bin/python3 src/server.py --sse
```

Expected — structured JSON logs, server ready:
```
{"time": "...", "level": "INFO", "message": "Uvicorn running on http://0.0.0.0:8000"}
```

**Open Terminal B for all curl and Python commands below.**

---

## 2. Health check

```bash
curl http://localhost:8000/health
```
```json
{"status": "healthy", "db": "connected"}
```

**Simulate DB failure** — shows 503 + retry behaviour:
```bash
brew services stop postgresql@16
curl http://localhost:8000/health
```
```json
{"status": "unhealthy", "db": "..."}
```

Watch Terminal A — tenacity retries fire automatically:
```
DB connection attempt 1 failed, retrying...
DB connection attempt 2 failed, retrying...
```

Restore:
```bash
brew services start postgresql@16
curl http://localhost:8000/health
```
```json
{"status": "healthy", "db": "connected"}
```

---

## 3. Prometheus metrics

```bash
curl http://localhost:8000/metrics
```

Key lines to point out:
```
db_pool_connections_available 2.0     ← pool live, 2 idle connections (minconn=2)
mcp_profile_cache_hits_total 0.0      ← no tool calls yet
mcp_tool_calls_total                  ← empty until tools are called
```

---

## 4. Auth middleware (API key enforcement)

Restart server with auth enabled:
```bash
# Ctrl+C in Terminal A, then:
export MCP_API_KEY=demosecret
.venv/bin/python3 src/server.py --sse
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

Disable auth for remaining steps:
```bash
# Ctrl+C, then:
unset MCP_API_KEY
.venv/bin/python3 src/server.py --sse
```

---

## 5. Query safety — blocked keywords & SELECT-only guard

```bash
.venv/bin/python3 test_manual.py
```

Expected (Test 4 section):
```
✓  'SELECT pg_sleep(100)'
   → Error: query contains a blocked keyword. System functions and file operations are not permitted.
✓  'SELECT pg_read_file("/etc")'
   → Error: query contains a blocked keyword. System functions and file operations are not permitted.
✓  'INSERT INTO transactions'
   → Error: only SELECT queries are allowed.
✓  'DROP TABLE transactions'
   → Error: only SELECT queries are allowed.
```

Point out: `duration=0.000s` in Terminal A — checks fire before any DB call.

---

## 6. TTLCache — profile caching

```bash
.venv/bin/python3 test_manual.py
```

Expected (Test 5 section):
```
Call 1 (cold) — expect DB query + cache miss
  duration=0.048s   misses: 1.0  hits: 0.0

Call 2 (warm) — expect cache hit, no DB query
  duration=0.000s   misses: 1.0  hits: 1.0

Call 3 (warm) — expect cache hit again
  duration=0.000s   misses: 1.0  hits: 2.0

✓  1 miss + 2 hits recorded correctly
```

First call hits DB (48ms). Next two served from in-memory cache (0ms).

---

## 7. Metrics after tool calls

```bash
curl http://localhost:8000/metrics | grep mcp_tool
```

```
mcp_tool_calls_total{tool="get_user_profile",status="success"} 3.0
mcp_tool_duration_seconds_sum{tool="get_user_profile"} 0.048
mcp_profile_cache_hits_total 2.0
mcp_profile_cache_misses_total 1.0
```

---

## 8. Claude Code — live tool calls

Connect the MCP server (one-time):
```bash
claude mcp add --transport sse fintech-fraud http://localhost:8000/sse
```

Open Claude Code:
```bash
claude
```

Verify connection:
```
/mcp
```
Expected: `fintech-fraud` listed as connected.

**Demo sequence in Claude:**

```
Run get_fraud_summary
```
Returns instantly from the materialized view — no heavy queries at call time.

```
Get the profile for user 10
```
Watch Terminal A — first call logs `duration=~50ms`. Ask again:
```
Get the profile for user 10 again
```
Second call logs `duration=0.000s` — served from cache.

```
Detect location anomalies with a 20-minute window
```
Runs the impossible-travel detector live against the transactions table.

```
Call refresh_fraud_summary
```
Returns immediately. Watch Terminal A for the background completion:
```json
{"message": "fraud_user_flags refresh completed"}
```

```
Which users appear in more than one fraud pattern?
```
Claude reads `get_fraud_summary` and reasons over the high-risk section.

---

## 9. Structured logs — trace ID correlation

In Terminal A, find any tool call in the logs. All lines for one invocation share the same `trace_id`:

```json
{"trace_id": "a3f9c1b2d4e8", "message": "tool=get_fraud_summary trace=a3f9c1b2d4e8 started"}
{"trace_id": "a3f9c1b2d4e8", "message": "tool=get_fraud_summary trace=a3f9c1b2d4e8 finished duration=0.043s status=success"}
```

Filter a single request end-to-end:
```bash
# In a third terminal, filter by trace ID (replace with one from your logs)
grep "a3f9c1b2d4e8" <(journalctl) 2>/dev/null || echo "grep Terminal A output for the trace_id"
```

---

## Summary — what this demo covers

| Capability | How shown |
|------------|-----------|
| Connection pooling | `db_pool_connections_available` gauge in `/metrics` |
| Retry on DB failure | `brew services stop` → retry log lines → clean error |
| Structured logging | JSON lines with `trace_id` in Terminal A |
| Prometheus metrics | `/metrics` before and after tool calls |
| API key auth | 401 without key, 200 with key, health always exempt |
| Query safety | Blocked keywords + SELECT-only guard, `duration=0.000s` |
| In-memory cache | 48ms cold → 0ms warm, counters in `/metrics` |
| Materialized view | `get_fraud_summary` instant read, `refresh_fraud_summary` background |
| Background threads | Refresh returns immediately, completion logged seconds later |
| MCP + Claude | Live fraud detection reasoning over real DB data |
