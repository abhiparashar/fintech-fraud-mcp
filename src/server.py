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

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

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

            rows = cur.fetchall()
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


if __name__ == "__main__":
    mcp.run(transport="sse")
