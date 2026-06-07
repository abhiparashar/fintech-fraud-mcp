-- Read-only database user for the query_transactions tool.
-- Limits blast radius if arbitrary SQL is passed — this user can only SELECT,
-- and only on the two tables the fraud server needs.
--
-- Run once: psql -U postgres -d fintechdb -f migrations/002_readonly_user.sql
-- Then set env vars before starting the server:
--   DB_READONLY_USER=fraud_reader
--   DB_READONLY_PASSWORD=<strong-password>

CREATE USER fraud_reader WITH PASSWORD 'readonly_password';

GRANT CONNECT ON DATABASE fintechdb TO fraud_reader;
GRANT USAGE  ON SCHEMA public       TO fraud_reader;
GRANT SELECT ON transactions        TO fraud_reader;
GRANT SELECT ON fraud_user_flags    TO fraud_reader;
