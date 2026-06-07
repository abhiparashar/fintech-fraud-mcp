-- Schema and seed data for local development / Docker.
-- Runs automatically when the postgres container starts for the first time.
-- Includes intentional fraud patterns so all 4 detectors return results immediately.

CREATE TABLE IF NOT EXISTS transactions (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER        NOT NULL,
    merchant   TEXT           NOT NULL,
    amount     NUMERIC(10, 2) NOT NULL,
    category   TEXT           NOT NULL,
    location   TEXT           NOT NULL,
    ip_address TEXT           NOT NULL,
    txn_date   TIMESTAMP      NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_txn_user_date ON transactions (user_id, txn_date);

-- ── Normal baseline (75 transactions, 15 users, establishes spending averages) ─

INSERT INTO transactions (user_id, merchant, amount, category, location, ip_address, txn_date) VALUES

-- User 1  (Mumbai, avg ~540)
(1, 'Swiggy',    450, 'Food',          'Mumbai', '192.168.1.1',  '2026-01-01 12:30:00'),
(1, 'BigBasket', 850, 'Groceries',     'Mumbai', '192.168.1.1',  '2026-01-03 10:00:00'),
(1, 'Uber',      300, 'Transport',     'Mumbai', '192.168.1.1',  '2026-01-05 09:00:00'),
(1, 'Netflix',   499, 'Entertainment', 'Mumbai', '192.168.1.1',  '2026-01-07 20:00:00'),
(1, 'Zomato',    620, 'Food',          'Mumbai', '192.168.1.1',  '2026-01-10 13:00:00'),

-- User 2  (Delhi, avg ~800)
(2, 'Amazon',    1200, 'Shopping',     'Delhi',  '10.0.0.2',     '2026-01-01 11:00:00'),
(2, 'Uber',       350, 'Transport',    'Delhi',  '10.0.0.2',     '2026-01-03 08:30:00'),
(2, 'Zomato',     750, 'Food',         'Delhi',  '10.0.0.2',     '2026-01-05 19:00:00'),
(2, 'PhonePe',    600, 'Transfer',     'Delhi',  '10.0.0.2',     '2026-01-08 15:00:00'),
(2, 'BigBasket',  900, 'Groceries',    'Delhi',  '10.0.0.2',     '2026-01-10 10:00:00'),

-- User 3  (Mumbai, avg ~590)
(3, 'Myntra',    800, 'Shopping',      'Mumbai', '192.168.3.1',  '2026-01-02 14:00:00'),
(3, 'Swiggy',    550, 'Food',          'Mumbai', '192.168.3.1',  '2026-01-04 12:00:00'),
(3, 'CRED',      600, 'Finance',       'Mumbai', '192.168.3.1',  '2026-01-06 16:00:00'),
(3, 'Uber',      400, 'Transport',     'Mumbai', '192.168.3.1',  '2026-01-09 09:30:00'),
(3, 'Hotstar',   299, 'Entertainment', 'Mumbai', '192.168.3.1',  '2026-01-11 21:00:00'),

-- User 4  (Chennai, avg ~560)
(4, 'Amazon',    750, 'Shopping',      'Chennai','172.16.0.4',   '2026-01-02 10:00:00'),
(4, 'Swiggy',    500, 'Food',          'Chennai','172.16.0.4',   '2026-01-04 13:00:00'),
(4, 'Ola',       350, 'Transport',     'Chennai','172.16.0.4',   '2026-01-06 08:00:00'),
(4, 'BigBasket', 700, 'Groceries',     'Chennai','172.16.0.4',   '2026-01-09 11:00:00'),
(4, 'Netflix',   499, 'Entertainment', 'Chennai','172.16.0.4',   '2026-01-12 20:00:00'),

-- User 5  (Bangalore, avg ~526)
(5, 'Flipkart',  600, 'Shopping',      'Bangalore','172.16.0.5', '2026-01-01 15:00:00'),
(5, 'Zomato',    480, 'Food',          'Bangalore','172.16.0.5', '2026-01-03 12:30:00'),
(5, 'Rapido',    200, 'Transport',     'Bangalore','172.16.0.5', '2026-01-05 08:30:00'),
(5, 'GPay',      750, 'Transfer',      'Bangalore','172.16.0.5', '2026-01-07 16:00:00'),
(5, 'Swiggy',    600, 'Food',          'Bangalore','172.16.0.5', '2026-01-10 19:00:00'),

-- User 6  (Goa, avg ~550)
(6, 'Amazon',    700, 'Shopping',      'Goa',    '172.16.0.6',   '2026-01-02 11:00:00'),
(6, 'Swiggy',    450, 'Food',          'Goa',    '172.16.0.6',   '2026-01-04 12:00:00'),
(6, 'BookMyShow',600, 'Entertainment', 'Goa',    '172.16.0.6',   '2026-01-06 18:00:00'),
(6, 'Uber',      400, 'Transport',     'Goa',    '172.16.0.6',   '2026-01-09 09:00:00'),
(6, 'BigBasket', 600, 'Groceries',     'Goa',    '172.16.0.6',   '2026-01-11 10:00:00'),

-- User 7  (Delhi, avg ~840)
(7, 'Amazon',   1100, 'Shopping',      'Delhi',  '10.0.0.7',     '2026-01-01 14:00:00'),
(7, 'Zomato',    800, 'Food',          'Delhi',  '10.0.0.7',     '2026-01-03 19:00:00'),
(7, 'Uber',      500, 'Transport',     'Delhi',  '10.0.0.7',     '2026-01-05 08:00:00'),
(7, 'CRED',      900, 'Finance',       'Delhi',  '10.0.0.7',     '2026-01-08 15:00:00'),
(7, 'BigBasket', 900, 'Groceries',     'Delhi',  '10.0.0.7',     '2026-01-10 11:00:00'),

-- User 8  (Hyderabad, avg ~720)
(8, 'Flipkart',  900, 'Shopping',      'Hyderabad','10.10.0.8',  '2026-01-02 14:00:00'),
(8, 'Swiggy',    600, 'Food',          'Hyderabad','10.10.0.8',  '2026-01-04 12:00:00'),
(8, 'Ola',       400, 'Transport',     'Hyderabad','10.10.0.8',  '2026-01-06 09:00:00'),
(8, 'Netflix',   499, 'Entertainment', 'Hyderabad','10.10.0.8',  '2026-01-08 21:00:00'),
(8, 'BigBasket', 800, 'Groceries',     'Hyderabad','10.10.0.8',  '2026-01-11 10:00:00'),

-- User 9  (Chennai, avg ~680)
(9, 'Amazon',    850, 'Shopping',      'Chennai','10.10.0.9',    '2026-01-01 11:00:00'),
(9, 'Zomato',    600, 'Food',          'Chennai','10.10.0.9',    '2026-01-03 19:00:00'),
(9, 'Rapido',    300, 'Transport',     'Chennai','10.10.0.9',    '2026-01-05 08:00:00'),
(9, 'Hotstar',   499, 'Entertainment', 'Chennai','10.10.0.9',    '2026-01-07 21:00:00'),
(9, 'BigBasket', 750, 'Groceries',     'Chennai','10.10.0.9',    '2026-01-10 10:00:00'),

-- User 10 (Bangalore, avg ~860)
(10,'Myntra',   1100, 'Shopping',      'Bangalore','172.16.0.10','2026-01-01 15:00:00'),
(10,'Swiggy',    700, 'Food',          'Bangalore','172.16.0.10','2026-01-03 12:00:00'),
(10,'Uber',      500, 'Transport',     'Bangalore','172.16.0.10','2026-01-05 09:00:00'),
(10,'Netflix',   499, 'Entertainment', 'Bangalore','172.16.0.10','2026-01-07 20:00:00'),
(10,'BigBasket', 900, 'Groceries',     'Bangalore','172.16.0.10','2026-01-09 11:00:00'),

-- User 11 (Kolkata, avg ~480)
(11,'Flipkart',  600, 'Shopping',      'Kolkata','172.16.0.11',  '2026-01-02 13:00:00'),
(11,'Swiggy',    400, 'Food',          'Kolkata','172.16.0.11',  '2026-01-04 12:00:00'),
(11,'Ola',       250, 'Transport',     'Kolkata','172.16.0.11',  '2026-01-06 08:00:00'),
(11,'Hotstar',   299, 'Entertainment', 'Kolkata','172.16.0.11',  '2026-01-09 21:00:00'),
(11,'BigBasket', 850, 'Groceries',     'Kolkata','172.16.0.11',  '2026-01-11 10:00:00'),

-- User 12 (Mumbai, avg ~620)
(12,'Amazon',    800, 'Shopping',      'Mumbai', '192.168.12.1', '2026-01-01 14:00:00'),
(12,'Zomato',    550, 'Food',          'Mumbai', '192.168.12.1', '2026-01-03 19:00:00'),
(12,'Uber',      400, 'Transport',     'Mumbai', '192.168.12.1', '2026-01-06 09:00:00'),
(12,'Netflix',   499, 'Entertainment', 'Mumbai', '192.168.12.1', '2026-01-08 20:00:00'),
(12,'BigBasket', 850, 'Groceries',     'Mumbai', '192.168.12.1', '2026-01-10 11:00:00'),

-- User 13 (Pune, avg ~374)
(13,'Flipkart',  550, 'Shopping',      'Pune',   '172.16.0.13',  '2026-01-02 14:00:00'),
(13,'Swiggy',    400, 'Food',          'Pune',   '172.16.0.13',  '2026-01-04 12:00:00'),
(13,'Rapido',    200, 'Transport',     'Pune',   '172.16.0.13',  '2026-01-06 08:00:00'),
(13,'Spotify',   119, 'Entertainment', 'Pune',   '172.16.0.13',  '2026-01-09 20:00:00'),
(13,'BigBasket', 600, 'Groceries',     'Pune',   '172.16.0.13',  '2026-01-11 10:00:00'),

-- User 14 (Hyderabad, avg ~530)
(14,'Amazon',    700, 'Shopping',      'Hyderabad','172.16.0.14','2026-01-01 11:00:00'),
(14,'Zomato',    500, 'Food',          'Hyderabad','172.16.0.14','2026-01-03 19:00:00'),
(14,'Ola',       350, 'Transport',     'Hyderabad','172.16.0.14','2026-01-05 08:00:00'),
(14,'Hotstar',   299, 'Entertainment', 'Hyderabad','172.16.0.14','2026-01-07 21:00:00'),
(14,'BigBasket', 800, 'Groceries',     'Hyderabad','172.16.0.14','2026-01-09 10:00:00'),

-- User 15 (Jaipur, avg ~320)
(15,'Meesho',    450, 'Shopping',      'Jaipur', '172.16.0.15',  '2026-01-02 14:00:00'),
(15,'Swiggy',    350, 'Food',          'Jaipur', '172.16.0.15',  '2026-01-04 12:00:00'),
(15,'Rapido',    180, 'Transport',     'Jaipur', '172.16.0.15',  '2026-01-06 08:00:00'),
(15,'Spotify',   119, 'Entertainment', 'Jaipur', '172.16.0.15',  '2026-01-08 20:00:00'),
(15,'BigBasket', 500, 'Groceries',     'Jaipur', '172.16.0.15',  '2026-01-10 10:00:00'),

-- ── FRAUD PATTERN 1: Duplicate charges (users 3, 7, 10, 12) ──────────────────

-- User 3: double charge at Amazon, same IP → likely system glitch
(3, 'Amazon', 1299, 'Shopping', 'Mumbai', '192.168.3.1',   '2026-01-15 14:30:00'),
(3, 'Amazon', 1299, 'Shopping', 'Mumbai', '192.168.3.1',   '2026-01-15 14:30:28'),

-- User 7: duplicate at Flipkart, different IP → replay attack
(7, 'Flipkart', 4599, 'Shopping', 'Delhi', '10.0.0.7',      '2026-01-15 16:00:00'),
(7, 'Flipkart', 4599, 'Shopping', 'Delhi', '203.0.113.42',  '2026-01-15 16:00:45'),

-- User 10: duplicate at Myntra, same IP
(10,'Myntra', 2199, 'Shopping', 'Bangalore', '172.16.0.10', '2026-01-15 11:00:00'),
(10,'Myntra', 2199, 'Shopping', 'Bangalore', '172.16.0.10', '2026-01-15 11:00:52'),

-- User 12: duplicate at restaurant, different IP → replay attack
(12,'The Bombay Canteen', 3400, 'Food', 'Mumbai', '192.168.12.1', '2026-01-15 20:00:00'),
(12,'The Bombay Canteen', 3400, 'Food', 'Mumbai', '192.168.12.5', '2026-01-15 20:00:35'),

-- ── FRAUD PATTERN 2: Impossible location jumps (users 1, 5) ──────────────────

-- User 1: Mumbai at 10:00 → London at 10:20 (20 minutes, impossible travel)
(1, 'Cafe Coffee Day',  350, 'Food',     'Mumbai', '192.168.1.1',  '2026-01-15 10:00:00'),
(1, 'Harrods',         8500, 'Shopping', 'London', '203.0.113.10', '2026-01-15 10:20:00'),

-- User 5: Bangalore at 09:00 → Dubai at 09:25 (25 minutes, impossible travel)
(5, 'Starbucks',        320, 'Food',     'Bangalore', '172.16.0.5',   '2026-01-15 09:00:00'),
(5, 'Dubai Mall',     12000, 'Shopping', 'Dubai',     '198.51.100.5', '2026-01-15 09:25:00'),

-- ── FRAUD PATTERN 3: Late night large spends (users 2, 6, 9, 14) ─────────────

-- User 2:  avg ~800,  03:15 AM spend = ₹6400  (8.0x average)
(2, 'Taj Hotels',   6400, 'Travel',        'Delhi',     '10.0.0.2',     '2026-01-15 03:15:00'),
-- User 6:  avg ~550,  02:45 AM spend = ₹3000  (5.5x average)
(6, 'Casino Goa',   3000, 'Entertainment', 'Goa',       '172.16.0.6',   '2026-01-15 02:45:00'),
-- User 9:  avg ~680,  03:30 AM spend = ₹2800  (4.1x average)
(9, 'ITC Hotels',   2800, 'Travel',        'Chennai',   '10.10.0.9',    '2026-01-15 03:30:00'),
-- User 14: avg ~530,  02:10 AM spend = ₹3300  (6.2x average)
(14,'Leela Palace', 3300, 'Travel',        'Hyderabad', '172.16.0.14',  '2026-01-15 02:10:00'),

-- ── FRAUD PATTERN 4: Rapid fire (user 10) — 6 transactions in 58 seconds ─────

(10,'Paytm',   100, 'Transfer', 'Bangalore', '172.16.0.10', '2026-01-15 23:00:00'),
(10,'PhonePe', 150, 'Transfer', 'Bangalore', '172.16.0.10', '2026-01-15 23:00:10'),
(10,'GPay',    200, 'Transfer', 'Bangalore', '172.16.0.10', '2026-01-15 23:00:22'),
(10,'Paytm',   120, 'Transfer', 'Bangalore', '172.16.0.10', '2026-01-15 23:00:35'),
(10,'PhonePe', 180, 'Transfer', 'Bangalore', '172.16.0.10', '2026-01-15 23:00:47'),
(10,'GPay',     90, 'Transfer', 'Bangalore', '172.16.0.10', '2026-01-15 23:00:58');
