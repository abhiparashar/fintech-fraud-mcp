import sys
sys.path.insert(0, 'src')
from tools import query_transactions, get_user_profile, _profile_cache
from metrics import profile_cache_hits_total, profile_cache_misses_total

# ── Test 4: Query safety ──────────────────────────────────────────────────────

print("=== Test 4: Query safety ===\n")

cases = [
    ("SELECT pg_sleep(100)",      "blocked keyword"),
    ('SELECT pg_read_file("/etc")', "blocked keyword"),
    ("INSERT INTO transactions VALUES (1,1,'x',1,'x','x','x',NOW())", "only SELECT"),
    ("DROP TABLE transactions",   "only SELECT"),
]

all_passed = True
for sql, expect_fragment in cases:
    result = query_transactions(sql)
    label = f"'{sql[:40]}...'" if len(sql) > 40 else f"'{sql}'"
    if "Error" in result or "error" in result:
        marker = "✓"
    else:
        marker = "✗"
        all_passed = False
    print(f"  {marker}  {label}")
    print(f"       → {result.strip()[:80]}")

print(f"\n{'✓  All 4 safety checks passed' if all_passed else '✗  Some checks failed'}\n")

# ── Test 5: TTLCache hit/miss tracking ────────────────────────────────────────

print("=== Test 5: TTLCache hit/miss tracking ===\n")

_profile_cache.clear()
hits_before = profile_cache_hits_total._value.get()
miss_before = profile_cache_misses_total._value.get()

print("Call 1 (cold) — expect DB query + cache miss")
get_user_profile(1)
print(f"  misses: {profile_cache_misses_total._value.get() - miss_before}  hits: {profile_cache_hits_total._value.get() - hits_before}")

print("Call 2 (warm) — expect cache hit, no DB query")
get_user_profile(1)
print(f"  misses: {profile_cache_misses_total._value.get() - miss_before}  hits: {profile_cache_hits_total._value.get() - hits_before}")

print("Call 3 (warm) — expect cache hit again")
get_user_profile(1)
print(f"  misses: {profile_cache_misses_total._value.get() - miss_before}  hits: {profile_cache_hits_total._value.get() - hits_before}")

expected_misses = 1
expected_hits   = 2
m = profile_cache_misses_total._value.get() - miss_before
h = profile_cache_hits_total._value.get()   - hits_before
print(f"\n{'✓' if m == expected_misses and h == expected_hits else '✗'}  1 miss + 2 hits recorded correctly")
