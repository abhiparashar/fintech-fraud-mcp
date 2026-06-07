import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send
from tracing import get_trace_id
from app import mcp
import tools  # noqa: F401 — registers all @mcp.tool() decorators as a side effect


def _setup_logging() -> None:
    """JSON structured logging. Every line includes the active trace ID."""

    class _JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload: dict = {
                "time":     self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level":    record.levelname,
                "logger":   record.name,
                "trace_id": get_trace_id(),
                "message":  record.getMessage(),
            }
            if record.exc_info:
                payload["exc"] = self.formatException(record.exc_info)
            return json.dumps(payload)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


_mw_logger = logging.getLogger("auth")


def _parse_key_map(raw: str) -> dict[str, str]:
    """Parse MCP_API_KEY into {key: caller_identity}.

    Formats accepted:
      'secret'                     → {'secret': 'default'}
      'analyst:key1,admin:key2'    → {'key1': 'analyst', 'key2': 'admin'}

    Backward compatible — a plain key with no colon uses identity 'default'.
    """
    result: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            identity, key = entry.split(":", 1)
            result[key.strip()] = identity.strip()
        else:
            result[entry] = "default"
    return result


class _SlidingWindowRateLimiter:
    """Per-caller sliding window rate limiter.

    Stores a list of request timestamps per caller and evicts those older than
    the window on every check — O(n) per check but n is small for this workload.

    Configured via env vars:
      RATE_LIMIT_REQUESTS        — max requests per window (default 60)
      RATE_LIMIT_WINDOW_SECONDS  — window size in seconds (default 60)
    """

    def __init__(self) -> None:
        self.max_requests = int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
        self.window = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, caller: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            ts = self._timestamps[caller]
            # Evict timestamps outside the window
            self._timestamps[caller] = [t for t in ts if t > cutoff]
            if len(self._timestamps[caller]) >= self.max_requests:
                return False
            self._timestamps[caller].append(now)
            return True


_rate_limiter = _SlidingWindowRateLimiter()


class APIKeyMiddleware:
    """
    Raw ASGI middleware — checks X-API-Key before passing through.
    Must NOT extend BaseHTTPMiddleware: that class buffers the response body,
    which breaks SSE streaming (the connection never flushes to the client).

    Supports multiple callers:
      MCP_API_KEY=analyst1:key1,admin:key2

    Exempt: /health and /metrics so monitoring always works.
    No-op when MCP_API_KEY env var is unset (local dev needs no config).
    """
    _EXEMPT = frozenset({'/health', '/metrics'})

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            raw_key_env = os.environ.get("MCP_API_KEY", "").strip()
            if raw_key_env and path not in self._EXEMPT:
                key_map = _parse_key_map(raw_key_env)
                headers = dict(scope.get("headers", []))
                api_key = headers.get(b"x-api-key", b"").decode()
                if api_key not in key_map:
                    _mw_logger.warning(
                        "auth=rejected path=%s key_prefix=%s", path, api_key[:4] or "(none)"
                    )
                    response = JSONResponse({"error": "Unauthorized"}, status_code=401)
                    await response(scope, receive, send)
                    return
                caller = key_map[api_key]
                _mw_logger.info("auth=ok caller=%s path=%s", caller, path)
                if not _rate_limiter.is_allowed(caller):
                    _mw_logger.warning(
                        "rate_limit=exceeded caller=%s limit=%d/%ds",
                        caller, _rate_limiter.max_requests, _rate_limiter.window,
                    )
                    response = JSONResponse({"error": "Rate limit exceeded"}, status_code=429)
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


async def health(request: Request) -> JSONResponse:
    import psycopg2
    from db import DB_CONFIG
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.cursor().execute("SELECT 1")
        return JSONResponse({"status": "healthy", "db": "connected"})
    except Exception as e:
        return JSONResponse({"status": "unhealthy", "db": str(e)}, status_code=503)
    finally:
        if conn is not None:
            conn.close()


async def metrics_endpoint(request: Request) -> Response:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from db import _pool
    from metrics import db_pool_in_use, db_pool_available

    if _pool is not None:
        try:
            db_pool_in_use.set(len(_pool._used))
            db_pool_available.set(len(_pool._pool))
        except Exception:
            pass

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _start_scheduled_refresh(interval_seconds: int = 300) -> None:
    """Refresh the fraud materialized view on a fixed schedule.
    Runs in a daemon thread — dies with the process, no manual teardown needed.
    Interval is configurable via MV_REFRESH_INTERVAL_SECONDS env var (default 300).
    """
    sched_logger = logging.getLogger("scheduler")

    def _loop() -> None:
        sched_logger.info("scheduled refresh: starting, interval=%ds", interval_seconds)
        while True:
            time.sleep(interval_seconds)
            try:
                from tools import refresh_fraud_summary
                refresh_fraud_summary()
                sched_logger.info("scheduled refresh: triggered")
            except Exception:
                sched_logger.exception("scheduled refresh: failed")

    threading.Thread(target=_loop, daemon=True, name="mv-refresh-scheduler").start()


if __name__ == "__main__":
    _setup_logging()
    if "--sse" in sys.argv:
        interval = int(os.environ.get("MV_REFRESH_INTERVAL_SECONDS", "300"))
        _start_scheduled_refresh(interval)

        starlette_app = Starlette(routes=[
            Route("/health", health, methods=["GET"]),
            Route("/metrics", metrics_endpoint, methods=["GET"]),
            Mount("/", app=mcp.sse_app()),
        ])
        app = APIKeyMiddleware(starlette_app)
        uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
    else:
        mcp.run(transport="stdio")
