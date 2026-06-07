import json
import logging
import os
import sys
import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
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


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Checks the X-API-Key header on every request except /health and /metrics.
    Enforcement is a no-op when MCP_API_KEY env var is not set, so local dev
    works without any configuration change.

    To enable: export MCP_API_KEY=<secret>
    Client config in ~/.claude.json:
      "headers": {"X-API-Key": "<secret>"}
    """
    _EXEMPT = frozenset({'/health', '/metrics'})

    async def dispatch(self, request: Request, call_next) -> Response:
        expected = os.environ.get("MCP_API_KEY")
        if expected and request.url.path not in self._EXEMPT:
            if request.headers.get("X-API-Key") != expected:
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    from db import _get_pool
    try:
        pool = _get_pool()
        conn = pool.getconn()
        pool.putconn(conn)
        return JSONResponse({"status": "healthy", "db": "connected"})
    except Exception as e:
        return JSONResponse({"status": "unhealthy", "db": str(e)}, status_code=503)


@mcp.custom_route("/metrics", methods=["GET"])
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
        app = mcp.sse_app()
        app.add_middleware(APIKeyMiddleware)
        uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
    else:
        mcp.run(transport="stdio")
