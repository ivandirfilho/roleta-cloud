\set ON_ERROR_STOP off
\echo '=== [03] TimescaleDB (best-effort, opcional) ==='
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        RAISE NOTICE '[OK] TimescaleDB v% instalado', (SELECT extversion FROM pg_extension WHERE extname='timescaledb');
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING '[SKIP] TimescaleDB indisponível: %', SQLERRM;
    END;
END $$;
\set ON_ERROR_STOP on
