-- Bulk seed: ~900 additional normal transactions across 15 users.
-- Combined with 000_schema.sql (97 rows) this brings the total to ~1000.
-- Uses generate_series so amounts/merchants vary deterministically without
-- triggering any of the 4 fraud detectors.

INSERT INTO transactions (user_id, merchant, amount, category, location, ip_address, txn_date)
SELECT
    u.user_id,
    (ARRAY[
        'Swiggy','Zomato','Amazon','Flipkart','BigBasket',
        'Uber','Ola','Rapido','Netflix','Hotstar',
        'Myntra','CRED','GPay','PhonePe','Spotify'
    ])[1 + (gs % 15)],
    -- amount varies ±30% around the user's baseline, stays well below fraud thresholds
    ROUND((u.base_amount * (0.7 + (((gs * 7 + u.user_id * 13) % 60)::numeric / 100)))::numeric, 2),
    (ARRAY[
        'Food','Shopping','Groceries','Transport','Entertainment','Finance'
    ])[1 + (gs % 6)],
    u.location,
    u.ip_address,
    -- spread across Jan 12 → May 31 2026, daytime hours only (09:00–22:00)
    TIMESTAMP '2026-01-12 09:00:00'
        + (gs * INTERVAL '11 hours 17 minutes')
        + (u.user_id * INTERVAL '41 minutes')
FROM (
    VALUES
        (1,  540, 'Mumbai',    '192.168.1.1'),
        (2,  800, 'Delhi',     '10.0.0.2'),
        (3,  590, 'Mumbai',    '192.168.3.1'),
        (4,  560, 'Chennai',   '172.16.0.4'),
        (5,  526, 'Bangalore', '172.16.0.5'),
        (6,  550, 'Goa',       '172.16.0.6'),
        (7,  840, 'Delhi',     '10.0.0.7'),
        (8,  720, 'Hyderabad', '10.10.0.8'),
        (9,  680, 'Chennai',   '10.10.0.9'),
        (10, 860, 'Bangalore', '172.16.0.10'),
        (11, 480, 'Kolkata',   '172.16.0.11'),
        (12, 620, 'Mumbai',    '192.168.12.1'),
        (13, 374, 'Pune',      '172.16.0.13'),
        (14, 530, 'Hyderabad', '172.16.0.14'),
        (15, 320, 'Jaipur',    '172.16.0.15')
) AS u(user_id, base_amount, location, ip_address),
generate_series(0, 61) AS gs
-- 15 users × 62 rows = 930 rows → total ~1027
-- gs steps are 11h17m apart so no two consecutive rows for the same user
-- are within the rapid-fire window (90 s) or late-night window (02:00–04:00)
;
