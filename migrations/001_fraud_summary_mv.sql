-- Materialized view: one row per (user_id, pattern).
-- Stores the result of all 4 fraud detectors so get_fraud_summary
-- reads from this table instead of running heavy self-joins on every call.
--
-- Refresh with: REFRESH MATERIALIZED VIEW CONCURRENTLY fraud_user_flags;
-- or call the refresh_fraud_summary MCP tool.

CREATE MATERIALIZED VIEW IF NOT EXISTS fraud_user_flags AS
WITH
  indian_cities AS (
    SELECT UNNEST(ARRAY[
      'Mumbai', 'Delhi', 'Bangalore', 'Chennai',
      'Hyderabad', 'Pune', 'Kolkata', 'Ahmedabad',
      'Jaipur', 'Surat', 'Lucknow', 'Kanpur'
    ]) AS city
  ),
  dup_users AS (
    SELECT DISTINCT a.user_id
    FROM transactions a
    JOIN transactions b
        ON  a.user_id  = b.user_id
        AND a.merchant = b.merchant
        AND a.amount   = b.amount
        AND a.txn_date < b.txn_date
        AND EXTRACT(EPOCH FROM (b.txn_date - a.txn_date)) < 60
  ),
  loc_users AS (
    SELECT DISTINCT a.user_id
    FROM transactions a
    JOIN transactions b
        ON  a.user_id  = b.user_id
        AND a.txn_date < b.txn_date
        AND a.location <> b.location
        AND EXTRACT(EPOCH FROM (b.txn_date - a.txn_date)) / 60 < 30
    WHERE a.location     IN  (SELECT city FROM indian_cities)
      AND b.location NOT IN  (SELECT city FROM indian_cities)
  ),
  late_users AS (
    SELECT DISTINCT t.user_id
    FROM transactions t
    JOIN (
        SELECT user_id, AVG(amount) AS avg_amt
        FROM transactions
        GROUP BY user_id
    ) u ON t.user_id = u.user_id
    WHERE EXTRACT(HOUR FROM t.txn_date) >= 2
      AND EXTRACT(HOUR FROM t.txn_date) <  4
      AND t.amount > 3.0 * u.avg_amt
  ),
  rapid_users AS (
    SELECT DISTINCT user_id FROM (
        SELECT a.user_id
        FROM transactions a
        JOIN transactions b
            ON  a.user_id = b.user_id
            AND b.txn_date BETWEEN
                a.txn_date - INTERVAL '90 seconds'
                AND
                a.txn_date + INTERVAL '90 seconds'
        GROUP BY a.user_id, a.txn_date, a.merchant, a.amount
        HAVING COUNT(b.*) >= 5
    ) s
  )
SELECT user_id, 'duplicate_charges'::text      AS pattern FROM dup_users
UNION
SELECT user_id, 'impossible_location'::text    AS pattern FROM loc_users
UNION
SELECT user_id, 'late_night_large_spend'::text AS pattern FROM late_users
UNION
SELECT user_id, 'rapid_fire'::text             AS pattern FROM rapid_users;

-- Required for REFRESH MATERIALIZED VIEW CONCURRENTLY
-- (concurrent refresh doesn't lock the view for reads)
CREATE UNIQUE INDEX IF NOT EXISTS idx_fraud_user_flags ON fraud_user_flags (user_id, pattern);
