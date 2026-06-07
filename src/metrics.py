from prometheus_client import Counter, Histogram, Gauge

tool_calls_total = Counter(
    'mcp_tool_calls_total',
    'Total MCP tool invocations',
    ['tool', 'status'],       # status: success | error
)

tool_duration_seconds = Histogram(
    'mcp_tool_duration_seconds',
    'MCP tool call latency in seconds',
    ['tool'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

db_pool_in_use = Gauge(
    'db_pool_connections_in_use',
    'DB connections currently checked out from the main pool',
)

db_pool_available = Gauge(
    'db_pool_connections_available',
    'DB connections idle in the main pool',
)

profile_cache_hits_total = Counter(
    'mcp_profile_cache_hits_total',
    'get_user_profile calls served from TTLCache (no DB query)',
)

profile_cache_misses_total = Counter(
    'mcp_profile_cache_misses_total',
    'get_user_profile calls that missed the cache and queried the DB',
)
