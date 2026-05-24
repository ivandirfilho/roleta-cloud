\set ON_ERROR_STOP on
\echo '=== [01] Extensões críticas ==='
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SELECT extname, extversion FROM pg_extension
 WHERE extname IN ('vector','age','pgcrypto','pg_stat_statements')
 ORDER BY extname;
