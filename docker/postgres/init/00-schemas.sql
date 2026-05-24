\set ON_ERROR_STOP on
\echo '=== [00] Schemas isolados por sentido (inegociável) ==='
CREATE SCHEMA IF NOT EXISTS cw;
CREATE SCHEMA IF NOT EXISTS ccw;
CREATE SCHEMA IF NOT EXISTS shared;
COMMENT ON SCHEMA cw  IS 'CW only. NUNCA mesclar com ccw.';
COMMENT ON SCHEMA ccw IS 'CCW only. NUNCA mesclar com cw.';
COMMENT ON SCHEMA shared IS 'Metadados não-direcionais.';
ALTER DATABASE roleta SET search_path TO shared, public;
