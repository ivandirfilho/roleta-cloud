\set ON_ERROR_STOP on
\echo '=== [01] Extensões críticas ==='
-- H7 (03/08): AGE e TimescaleDB removidos — nunca saíram do CREATE EXTENSION
-- (0 grafos consultados, 0 hypertables). Stack simplificada para pgvector
-- upstream (pgvector/pgvector:pg15) = imagem oficial, sem build custom.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SELECT extname, extversion FROM pg_extension
 WHERE extname IN ('vector','pgcrypto','pg_stat_statements')
 ORDER BY extname;
