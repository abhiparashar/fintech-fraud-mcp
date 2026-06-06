import psycopg2
import psycopg2.extras

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
