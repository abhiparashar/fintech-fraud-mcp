import json
import logging
import sys
from starlette.requests import Request
from starlette.responses import JSONResponse
from app import mcp
import tools  # noqa: F401 — registers all @mcp.tool() decorators as a side effect


def _setup_logging() -> None:
    class _JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload: dict = {
                "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exc"] = self.formatException(record.exc_info)
            return json.dumps(payload)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


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


if __name__ == "__main__":
    _setup_logging()
    transport = "sse" if "--sse" in sys.argv else "stdio"
    mcp.run(transport=transport)
