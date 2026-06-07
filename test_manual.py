import sys
sys.path.insert(0, 'src')
from tools import query_transactions, get_user_profile, _profile_cache
from metrics import profile_cache_hits_total, profile_cache_misses_total

print("=== Test 5: TTLCache hit/miss tracking ===\n")

_profile_cache.clear()
hits_before  = profile_cache_hits_total._value.get()
miss_before  = profile_cache_misses_total._value.get()

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
