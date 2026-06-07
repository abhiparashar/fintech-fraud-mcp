import uuid
from contextvars import ContextVar

# One trace ID per tool call, stored in a context variable so it flows
# automatically through the call stack without being passed as a parameter.
# Works correctly with Python threads (each thread has its own context).

_trace_id: ContextVar[str] = ContextVar('trace_id', default='-')


def new_trace_id() -> str:
    """Generate a fresh trace ID and bind it to the current context."""
    tid = uuid.uuid4().hex[:12]
    _trace_id.set(tid)
    return tid


def get_trace_id() -> str:
    """Read the trace ID bound to the current context."""
    return _trace_id.get()
