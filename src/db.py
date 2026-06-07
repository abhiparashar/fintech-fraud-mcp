import os
import time
import functools
import logging
import threading
import psycopg2
import psycopg2.extras
import psycopg2.pool
import psycopg2.extensions
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random, retry_if_exception_type
from tracing import new_trace_id, get_trace_id
from metrics import tool_calls_total, tool_duration_seconds

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "localhost"),
    "port":     int(os.environ.get("DB_PORT", "5432")),
    "database": os.environ.get("DB_NAME",     "fintechdb"),
    "user":     os.environ.get("DB_USER",     "postgres"),
    "password": os.environ.get("DB_PASSWORD", "password"),
    "connect_timeout": 5,
    "options": "-c statement_timeout=10000",
}

# Separate config for the read-only pool used by query_transactions.
# Uses fraud_reader user which has SELECT-only access — limits blast radius
# if arbitrary SQL is passed. Run migrations/002_readonly_user.sql first.
READONLY_DB_CONFIG = {
    **DB_CONFIG,
    "user":     os.environ.get("DB_READONLY_USER",     "fraud_reader"),
    "password": os.environ.get("DB_READONLY_PASSWORD", "readonly_password"),
}

INDIAN_CITIES = (
    'Mumbai', 'Delhi', 'Bangalore', 'Chennai',
    'Hyderabad', 'Pune', 'Kolkata', 'Ahmedabad',
    'Jaipur', 'Surat', 'Lucknow', 'Kanpur'
)

# ── main connection pool ──────────────────────────────────────────────────────

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2, maxconn=20, **DB_CONFIG
                )
                logger.info("main DB pool initialised (min=2, max=20)")
    return _pool


@retry(
    retry=retry_if_exception_type((psycopg2.OperationalError, psycopg2.pool.PoolError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5) + wait_random(0, 1),
    reraise=True,
    before_sleep=lambda rs: logger.warning(
        "DB connection attempt %d failed, retrying...", rs.attempt_number
    ),
)
def get_connection() -> psycopg2.extensions.connection:
    return _get_pool().getconn()


def release_connection(conn: psycopg2.extensions.connection) -> None:
    if not (_pool and conn):
        return
    try:
        if conn.status != psycopg2.extensions.STATUS_READY:
            conn.rollback()
        conn.autocommit = False
    except Exception:
        pass
    _pool.putconn(conn)


# ── read-only pool (query_transactions only) ──────────────────────────────────

_readonly_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_readonly_pool_lock = threading.Lock()


def _get_readonly_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _readonly_pool
    if _readonly_pool is None:
        with _readonly_pool_lock:
            if _readonly_pool is None:
                _readonly_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1, maxconn=5, **READONLY_DB_CONFIG
                )
                logger.info(
                    "readonly DB pool initialised user=%s (min=1, max=5)",
                    READONLY_DB_CONFIG["user"],
                )
    return _readonly_pool


@retry(
    retry=retry_if_exception_type((psycopg2.OperationalError, psycopg2.pool.PoolError)),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=3) + wait_random(0, 1),
    reraise=True,
)
def get_readonly_connection() -> psycopg2.extensions.connection:
    return _get_readonly_pool().getconn()


def release_readonly_connection(conn: psycopg2.extensions.connection) -> None:
    if not (_readonly_pool and conn):
        return
    try:
        if conn.status != psycopg2.extensions.STATUS_READY:
            conn.rollback()
        conn.autocommit = False
    except Exception:
        pass
    _readonly_pool.putconn(conn)


# ── error handler + observability decorator ───────────────────────────────────
# Applied to every MCP tool. Sets a trace ID, records Prometheus metrics,
# logs start/end with duration, and converts raw psycopg2 exceptions into
# clean messages so internal details never reach Claude.

def handle_db_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        tid = new_trace_id()
        start = time.perf_counter()
        status = 'success'
        logger.info("tool=%s trace=%s started", fn.__name__, tid)
        try:
            return fn(*args, **kwargs)
        except psycopg2.OperationalError as e:
            status = 'error'
            logger.error("tool=%s trace=%s DB unavailable: %s", fn.__name__, tid, e)
            return "Database temporarily unavailable. Please try again in a moment."
        except psycopg2.Error as e:
            status = 'error'
            logger.error(
                "tool=%s trace=%s DB error [%s]: %s", fn.__name__, tid, type(e).__name__, e
            )
            return "A database error occurred. Check server logs for details."
        except Exception:
            status = 'error'
            logger.exception("tool=%s trace=%s unexpected error", fn.__name__, tid)
            return "An unexpected error occurred. Check server logs."
        finally:
            duration = time.perf_counter() - start
            tool_calls_total.labels(tool=fn.__name__, status=status).inc()
            tool_duration_seconds.labels(tool=fn.__name__).observe(duration)
            logger.info(
                "tool=%s trace=%s finished duration=%.3fs status=%s",
                fn.__name__, tid, duration, status,
            )
    return wrapper


# ── private query helpers ─────────────────────────────────────────────────────

def _fetch_duplicate_rows(cur, threshold_seconds: int = 60):
    cur.execute("""
        SELECT
            a.user_id,
            a.merchant,
            a.amount,
            a.txn_date    AS first_txn,
            b.txn_date    AS second_txn,
            EXTRACT(EPOCH FROM (b.txn_date - a.txn_date))::int AS seconds_apart,
            a.ip_address  AS ip_first,
            b.ip_address  AS ip_second,
            a.location    AS location_first,
            b.location    AS location_second
        FROM transactions a
        JOIN transactions b
            ON  a.user_id  = b.user_id
            AND a.merchant = b.merchant
            AND a.amount   = b.amount
            AND a.txn_date < b.txn_date
            AND EXTRACT(EPOCH FROM (b.txn_date - a.txn_date)) < %s
        ORDER BY a.user_id, a.txn_date
    """, (threshold_seconds,))
    return cur.fetchall()


def _fetch_location_anomaly_rows(cur, threshold_minutes: int = 30):
    cur.execute("""
        SELECT
            a.user_id,
            a.location                                              AS location_first,
            b.location                                              AS location_second,
            a.txn_date                                              AS time_first,
            b.txn_date                                              AS time_second,
            EXTRACT(EPOCH FROM (b.txn_date - a.txn_date))::int / 60 AS minutes_apart,
            a.merchant                                              AS merchant_first,
            b.merchant                                              AS merchant_second,
            a.amount                                                AS amount_first,
            b.amount                                                AS amount_second,
            a.ip_address                                            AS ip_first,
            b.ip_address                                            AS ip_second
        FROM transactions a
        JOIN transactions b
            ON  a.user_id  = b.user_id
            AND a.txn_date < b.txn_date
            AND a.location <> b.location
            AND EXTRACT(EPOCH FROM (b.txn_date - a.txn_date)) / 60 < %s
        WHERE
            a.location = ANY(%s) AND b.location <> ALL(%s)
        ORDER BY a.user_id, a.txn_date
    """, (threshold_minutes, list(INDIAN_CITIES), list(INDIAN_CITIES)))
    return cur.fetchall()


def _fetch_late_night_rows(cur, start_hour: int = 2, end_hour: int = 4, multiplier: float = 3.0):
    cur.execute("""
        WITH user_averages AS (
            SELECT
                user_id,
                ROUND(AVG(amount)::numeric, 2) AS avg_amount
            FROM transactions
            GROUP BY user_id
        )
        SELECT
            t.user_id,
            t.merchant,
            t.amount,
            ROUND(u.avg_amount::numeric, 2)              AS user_avg_amount,
            ROUND((t.amount / u.avg_amount)::numeric, 1) AS times_above_avg,
            t.txn_date,
            t.location,
            t.ip_address,
            t.category
        FROM transactions t
        JOIN user_averages u ON t.user_id = u.user_id
        WHERE
            EXTRACT(HOUR FROM t.txn_date) >= %s
            AND EXTRACT(HOUR FROM t.txn_date) < %s
            AND t.amount > %s * u.avg_amount
        ORDER BY t.amount DESC
    """, (start_hour, end_hour, multiplier))
    return cur.fetchall()


def _fetch_rapid_fire_rows(cur, window_seconds: int = 90, min_txn_count: int = 5):
    cur.execute("""
        WITH burst_check AS (
            SELECT
                a.user_id,
                a.txn_date,
                a.merchant,
                a.amount,
                COUNT(b.*) AS nearby_count
            FROM transactions a
            JOIN transactions b
                ON  a.user_id = b.user_id
                AND b.txn_date BETWEEN
                    a.txn_date - INTERVAL '1 second' * %s
                    AND
                    a.txn_date + INTERVAL '1 second' * %s
            GROUP BY a.user_id, a.txn_date, a.merchant, a.amount
            HAVING COUNT(b.*) >= %s
        )
        SELECT
            user_id,
            COUNT(*)                                                 AS flagged_txn_count,
            MIN(txn_date)                                            AS burst_start,
            MAX(txn_date)                                            AS burst_end,
            EXTRACT(EPOCH FROM (MAX(txn_date) - MIN(txn_date)))::int AS duration_seconds,
            SUM(amount)                                              AS total_amount,
            STRING_AGG(DISTINCT merchant, ', ')                      AS merchants
        FROM burst_check
        GROUP BY user_id
        ORDER BY flagged_txn_count DESC
    """, (window_seconds, window_seconds, min_txn_count))
    return cur.fetchall()
