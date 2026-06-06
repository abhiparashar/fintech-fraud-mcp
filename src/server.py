import psycopg2
import psycopg2.extras
from mcp.server.fastmcp import FastMCP

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "fintechdb",
    "user": "postgres",
    "password": "password",
}

INDIAN_CITIES = (
    'Mumbai', 'Delhi', 'Bangalore', 'Chennai',
    'Hyderabad', 'Pune', 'Kolkata', 'Ahmedabad',
    'Jaipur', 'Surat', 'Lucknow', 'Kanpur'
)


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# ─── private query helpers ────────────────────────────────────────────────────

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


# ─── MCP server ───────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="fintech-fraud-mcp",
    instructions="You are a fintech fraud detection assistant. Use the available tools to query transactions and identify anomalies.",
)


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
    Run all fraud detectors in one shot and return a consolidated report.
    Highlights users who appear in multiple fraud patterns — the highest risk cases.
    Use this as the starting point for any fraud investigation.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            dup_rows   = _fetch_duplicate_rows(cur)
            loc_rows   = _fetch_location_anomaly_rows(cur)
            late_rows  = _fetch_late_night_rows(cur)
            rapid_rows = _fetch_rapid_fire_rows(cur)

        dup_users   = {row['user_id'] for row in dup_rows}
        loc_users   = {row['user_id'] for row in loc_rows}
        late_users  = {row['user_id'] for row in late_rows}
        rapid_users = {row['user_id'] for row in rapid_rows}

        all_flagged: dict[int, list[str]] = {}
        for uid in dup_users:
            all_flagged.setdefault(uid, []).append("duplicate charges")
        for uid in loc_users:
            all_flagged.setdefault(uid, []).append("impossible location")
        for uid in late_users:
            all_flagged.setdefault(uid, []).append("late night large spend")
        for uid in rapid_users:
            all_flagged.setdefault(uid, []).append("rapid fire")

        high_risk = {uid: flags for uid, flags in all_flagged.items() if len(flags) >= 2}

        report = [
            "FRAUD SUMMARY REPORT",
            "=" * 40,
            f"Duplicate charge pairs     : {len(dup_rows)}   (users: {sorted(dup_users) or 'none'})",
            f"Impossible location jumps  : {len(loc_rows)}   (users: {sorted(loc_users) or 'none'})",
            f"Late night large spends    : {len(late_rows)}   (users: {sorted(late_users) or 'none'})",
            f"Rapid fire bursts          : {len(rapid_rows)}   (users: {sorted(rapid_users) or 'none'})",
            f"\nTotal flagged users        : {len(all_flagged)}",
            "",
            "HIGH RISK USERS (2+ fraud patterns)",
            "-" * 40,
        ]

        if high_risk:
            for uid, flags in sorted(high_risk.items()):
                report.append(f"  user {uid} → {' + '.join(flags)}")
        else:
            report.append("  None found.")

        return "\n".join(report)
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    transport = "sse" if "--sse" in sys.argv else "stdio"
    mcp.run(transport=transport)
