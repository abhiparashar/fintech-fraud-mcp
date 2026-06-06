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


if __name__ == "__main__":
    mcp.run(transport="sse")
