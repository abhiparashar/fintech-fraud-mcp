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

if __name__ == "__main__":
    mcp.run(transport="sse")
