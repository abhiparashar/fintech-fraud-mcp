import psycopg2.extras
from threading import RLock
from cachetools import TTLCache, cached
from app import mcp
from db import (
    get_connection,
    _fetch_duplicate_rows,
    _fetch_location_anomaly_rows,
    _fetch_late_night_rows,
    _fetch_rapid_fire_rows,
)

_profile_cache: TTLCache = TTLCache(maxsize=500, ttl=300)
_profile_lock = RLock()


@mcp.tool()
def get_schema() -> str:
    """Get the column names and data types of the transactions table."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'transactions'
                ORDER BY ordinal_position
            """)
            rows = cur.fetchall()
            result = "\n".join(
                f"{row['column_name']} | {row['data_type']} | nullable: {row['is_nullable']}"
                for row in rows
            )
            return f"transactions table schema:\n\n{result}"
    finally:
        conn.close()


@mcp.tool()
def query_transactions(sql: str) -> str:
    """
    Run a read-only SELECT query on the transactions table.
    Use this for ad-hoc analysis that other tools don't cover.
    """
    if not sql.strip().lower().startswith("select"):
        return "Error: only SELECT queries are allowed."

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            if not rows:
                return "No results found."
            result = "\n".join(str(dict(row)) for row in rows)
            return f"Query returned {len(rows)} row(s):\n\n{result}"
    except Exception as e:
        return f"Query error: {str(e)}"
    finally:
        conn.close()


@mcp.tool()
def detect_duplicate_transactions(threshold_seconds: int = 60) -> str:
    """
    Find duplicate transactions — same user, same amount, same merchant
    within a given time window (default 60 seconds).
    Returns each suspicious pair along with IP addresses to help
    distinguish a double charge from a replay attack.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = _fetch_duplicate_rows(cur, threshold_seconds)
            if not rows:
                return "No duplicate transactions found."

            result = []
            for row in rows:
                same_ip = row['ip_first'] == row['ip_second']
                hint = "likely double charge (same IP)" if same_ip else "suspicious — different IPs, possible replay attack"
                result.append(
                    f"user {row['user_id']} | {row['merchant']} | ₹{row['amount']} | "
                    f"{row['first_txn']} → {row['second_txn']} | "
                    f"{row['seconds_apart']}s apart | {hint}"
                )
            return f"Found {len(rows)} duplicate pair(s):\n\n" + "\n".join(result)
    finally:
        conn.close()


@mcp.tool()
def detect_location_anomalies(threshold_minutes: int = 30) -> str:
    """
    Find impossible location changes — same user appearing in an Indian city
    and a foreign location within a short time window.
    Flags likely card cloning or stolen card details used abroad.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = _fetch_location_anomaly_rows(cur, threshold_minutes)
            if not rows:
                return "No impossible location changes found."

            result = []
            for row in rows:
                result.append(
                    f"user {row['user_id']} | "
                    f"{row['location_first']} ({row['merchant_first']} ₹{row['amount_first']}) at {row['time_first']} → "
                    f"{row['location_second']} ({row['merchant_second']} ₹{row['amount_second']}) at {row['time_second']} | "
                    f"{row['minutes_apart']} min apart | "
                    f"IPs: {row['ip_first']} → {row['ip_second']}"
                )
            return f"Found {len(rows)} impossible location change(s):\n\n" + "\n".join(result)
    finally:
        conn.close()


@mcp.tool()
def detect_late_night_large_transactions(
    start_hour: int = 2,
    end_hour: int = 4,
    multiplier: float = 3.0
) -> str:
    """
    Find late night transactions that are significantly larger than a user's average spend.
    Default window is 2 AM to 4 AM with amount > 3x the user's historical average.
    Strong indicator of account takeover or stolen card usage.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = _fetch_late_night_rows(cur, start_hour, end_hour, multiplier)
            if not rows:
                return "No suspicious late night transactions found."

            result = []
            for row in rows:
                result.append(
                    f"user {row['user_id']} | {row['merchant']} | ₹{row['amount']} | "
                    f"{row['times_above_avg']}x their avg (₹{row['user_avg_amount']}) | "
                    f"{row['txn_date']} | {row['location']} | IP: {row['ip_address']}"
                )
            return f"Found {len(rows)} suspicious late night transaction(s):\n\n" + "\n".join(result)
    finally:
        conn.close()


@mcp.tool()
def detect_rapid_fire_transactions(
    window_seconds: int = 90,
    min_txn_count: int = 5
) -> str:
    """
    Find users who made many transactions within a short time window.
    Default: 5 or more transactions within 90 seconds.
    Strong indicator of bot activity or card testing.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = _fetch_rapid_fire_rows(cur, window_seconds, min_txn_count)
            if not rows:
                return "No rapid fire transaction bursts found."

            result = []
            for row in rows:
                result.append(
                    f"user {row['user_id']} | "
                    f"{row['flagged_txn_count']} transactions in {row['duration_seconds']}s | "
                    f"₹{row['total_amount']} total | "
                    f"burst: {row['burst_start']} → {row['burst_end']} | "
                    f"merchants: {row['merchants']}"
                )
            return f"Found {len(rows)} user(s) with rapid fire bursts:\n\n" + "\n".join(result)
    finally:
        conn.close()


@mcp.tool()
@cached(cache=_profile_cache, lock=_profile_lock)
def get_user_profile(user_id: int) -> str:
    """
    Get a full spending profile for a specific user.
    Use this before making a fraud judgement — understand what is
    normal for this user before flagging anything as suspicious.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*)                                        AS total_transactions,
                    ROUND(SUM(amount)::numeric, 2)                  AS total_spend,
                    ROUND(AVG(amount)::numeric, 2)                  AS avg_spend,
                    ROUND(MIN(amount)::numeric, 2)                  AS min_spend,
                    ROUND(MAX(amount)::numeric, 2)                  AS max_spend,
                    MIN(txn_date)                                   AS first_transaction,
                    MAX(txn_date)                                   AS last_transaction,
                    COUNT(DISTINCT merchant)                        AS unique_merchants,
                    COUNT(DISTINCT location)                        AS unique_locations,
                    MODE() WITHIN GROUP (ORDER BY location)         AS most_common_location,
                    MODE() WITHIN GROUP (ORDER BY category)         AS most_common_category
                FROM transactions
                WHERE user_id = %s
            """, (user_id,))
            summary = cur.fetchone()

            if not summary['total_transactions']:
                return f"No transactions found for user {user_id}."

            cur.execute("""
                SELECT category, COUNT(*) AS count, ROUND(SUM(amount)::numeric, 2) AS total
                FROM transactions
                WHERE user_id = %s
                GROUP BY category
                ORDER BY count DESC
            """, (user_id,))
            categories = cur.fetchall()

            cur.execute("""
                SELECT merchant, COUNT(*) AS count, ROUND(SUM(amount)::numeric, 2) AS total
                FROM transactions
                WHERE user_id = %s
                GROUP BY merchant
                ORDER BY count DESC
                LIMIT 5
            """, (user_id,))
            top_merchants = cur.fetchall()

            cur.execute("""
                SELECT
                    EXTRACT(HOUR FROM txn_date)::int AS hour,
                    COUNT(*) AS count
                FROM transactions
                WHERE user_id = %s
                GROUP BY hour
                ORDER BY count DESC
                LIMIT 3
            """, (user_id,))
            active_hours = cur.fetchall()

            category_breakdown = " | ".join(
                f"{r['category']}: {r['count']} txns (₹{r['total']})"
                for r in categories
            )
            merchant_breakdown = " | ".join(
                f"{r['merchant']} x{r['count']} (₹{r['total']})"
                for r in top_merchants
            )
            hours_breakdown = ", ".join(
                f"{r['hour']}:00 ({r['count']} txns)"
                for r in active_hours
            )

            return (
                f"User {user_id} Profile\n"
                f"{'─' * 40}\n"
                f"Total transactions : {summary['total_transactions']}\n"
                f"Total spend        : ₹{summary['total_spend']}\n"
                f"Average spend      : ₹{summary['avg_spend']}\n"
                f"Min / Max spend    : ₹{summary['min_spend']} / ₹{summary['max_spend']}\n"
                f"Active since       : {summary['first_transaction']}\n"
                f"Last transaction   : {summary['last_transaction']}\n"
                f"Unique merchants   : {summary['unique_merchants']}\n"
                f"Unique locations   : {summary['unique_locations']}\n"
                f"Most common city   : {summary['most_common_location']}\n"
                f"Most common cat    : {summary['most_common_category']}\n\n"
                f"Category breakdown : {category_breakdown}\n"
                f"Top merchants      : {merchant_breakdown}\n"
                f"Most active hours  : {hours_breakdown}"
            )
    finally:
        conn.close()


@mcp.tool()
def get_fraud_summary() -> str:
    """
    Return a pre-computed fraud summary from the fraud_user_flags materialized view.
    Instant read — no heavy queries at call time.
    Call refresh_fraud_summary first if you need up-to-the-minute results.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    pattern,
                    COUNT(*)                              AS user_count,
                    ARRAY_AGG(user_id ORDER BY user_id)   AS affected_users
                FROM fraud_user_flags
                GROUP BY pattern
                ORDER BY pattern
            """)
            stats = {row['pattern']: row for row in cur.fetchall()}

            cur.execute("""
                SELECT
                    user_id,
                    ARRAY_AGG(pattern ORDER BY pattern) AS patterns
                FROM fraud_user_flags
                GROUP BY user_id
                HAVING COUNT(*) >= 2
                ORDER BY user_id
            """)
            high_risk = cur.fetchall()

        pattern_labels = {
            'duplicate_charges':      'Duplicate charge users    ',
            'impossible_location':    'Impossible location jumps ',
            'late_night_large_spend': 'Late night large spends   ',
            'rapid_fire':             'Rapid fire bursts         ',
        }

        all_flagged_users: set[int] = set()
        report = ["FRAUD SUMMARY REPORT", "=" * 40]

        for key, label in pattern_labels.items():
            row = stats.get(key)
            if row:
                users = sorted(row['affected_users'])
                all_flagged_users.update(users)
                report.append(f"{label}: {row['user_count']}   (users: {users})")
            else:
                report.append(f"{label}: 0   (users: none)")

        report += [
            f"\nTotal flagged users        : {len(all_flagged_users)}",
            "",
            "HIGH RISK USERS (2+ fraud patterns)",
            "-" * 40,
        ]

        if high_risk:
            for row in high_risk:
                report.append(f"  user {row['user_id']} → {' + '.join(row['patterns'])}")
        else:
            report.append("  None found.")

        return "\n".join(report)
    except Exception as e:
        if 'fraud_user_flags' in str(e):
            return "Materialized view not found. Run: psql -U postgres -d fintechdb -f migrations/001_fraud_summary_mv.sql"
        raise
    finally:
        conn.close()


@mcp.tool()
def refresh_fraud_summary() -> str:
    """
    Refresh the fraud_user_flags materialized view with the latest transaction data.
    This re-runs all 4 fraud detection queries and stores the results.
    Call this after new transactions are added, then call get_fraud_summary to read results.
    """
    conn = get_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY fraud_user_flags")
        return "Refreshed. Call get_fraud_summary to see updated results."
    finally:
        conn.close()
