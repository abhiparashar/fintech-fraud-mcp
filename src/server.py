import json
import logging
import os
import sys
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


class APIKeyMiddleware:
    """
    Raw ASGI middleware — checks X-API-Key before passing through.
    Must NOT extend BaseHTTPMiddleware: that class buffers the response body,
    which breaks SSE streaming (the connection never flushes to the client).

    Exempt: /health and /metrics so monitoring always works.
    No-op when MCP_API_KEY env var is unset (local dev needs no config).
    """
    _EXEMPT = frozenset({'/health', '/metrics'})

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            expected = os.environ.get("MCP_API_KEY")
            if expected and path not in self._EXEMPT:
                headers = dict(scope.get("headers", []))
                api_key = headers.get(b"x-api-key", b"").decode()
                if api_key != expected:
                    response = JSONResponse({"error": "Unauthorized"}, status_code=401)
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


if __name__ == "__main__":
    _setup_logging()
    if "--sse" in sys.argv:
        starlette_app = Starlette(routes=[
            Route("/health", health, methods=["GET"]),
            Route("/metrics", metrics_endpoint, methods=["GET"]),
            Mount("/", app=mcp.sse_app()),
        ])
        app = APIKeyMiddleware(starlette_app)
        uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
    else:
        mcp.run(transport="stdio")
