# fintech-fraud-mcp

A Python MCP (Model Context Protocol) server that connects Claude to a PostgreSQL transactions database and detects fraud patterns using SQL.

## What is MCP?

MCP is an open standard that lets AI models like Claude connect to external tools and data sources. Instead of Claude guessing about your data, it can call real functions — here, SQL queries against a live database — and reason over the actual results.

This server exposes 8 tools to Claude over **HTTP/SSE transport**, which means Claude connects to a running HTTP server rather than a subprocess. SSE (Server-Sent Events) lets the server push results back to Claude in a streaming fashion.

## Fraud patterns detected

| Tool | What it finds |
|------|---------------|
| `detect_duplicate_transactions` | Same user, same merchant, same amount within N seconds — double charges or replay attacks |
| `detect_location_anomalies` | User transacts in an Indian city then abroad within 30 minutes — impossible travel, likely stolen card |
| `detect_late_night_large_transactions` | Transactions between 2–4 AM that are 3x+ the user's average spend — account takeover signal |
| `detect_rapid_fire_transactions` | 5+ transactions within 90 seconds — bot activity or card testing |
| `get_fraud_summary` | Runs all four detectors and highlights users flagged by 2+ patterns (highest risk) |
| `get_user_profile` | Full spending profile for a user — baseline before making any fraud judgment |
| `get_schema` | Returns the transactions table schema |
| `query_transactions` | Ad-hoc read-only SQL for custom analysis |

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

# 4. Ensure PostgreSQL is running and fintechdb exists
brew services start postgresql@16
psql -U postgres -c "CREATE DATABASE fintechdb;" 2>/dev/null || true
```

## Running the server

```bash
# Start the MCP server on http://localhost:8000
.venv/bin/python3 src/server.py --sse
```

The server starts with Uvicorn and listens on port 8000.

## Connecting to Claude Code

Register the server once:

```bash
claude mcp add --transport sse fintech-fraud-mcp http://localhost:8000/sse
```

Then start the server and open Claude Code. The 8 tools appear automatically. Ask Claude things like:

- *"Run get_fraud_summary"*
- *"Get the profile for user 10"*
- *"Detect location anomalies with a 20-minute window"*
- *"Which users appear in multiple fraud patterns?"*

## Project structure

```
src/
  app.py      — FastMCP instance (mcp singleton)
  db.py       — DB connection config + SQL query helpers (_fetch_* functions)
  tools.py    — All 8 @mcp.tool() definitions, imports from app.py and db.py
  server.py   — Entry point: imports tools to register them, calls mcp.run()
```

**Why this separation:**

- `db.py` is the SQL layer — change a query, go here
- `tools.py` is the formatting layer — change what Claude sees, go here
- `app.py` is the singleton — avoids circular imports between tools and server
- `server.py` stays tiny — 5 lines, just wires everything and starts

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
```

## Tech stack

- **FastMCP** — Python SDK for the Model Context Protocol
- **Uvicorn** — ASGI server that runs the SSE endpoint
- **Starlette** — Web framework underneath FastMCP's SSE transport
- **psycopg2** — PostgreSQL driver
