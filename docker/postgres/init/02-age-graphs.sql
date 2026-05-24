\set ON_ERROR_STOP on
\echo '=== [02] Grafos AGE isolados ==='
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('cw_graph');
SELECT create_graph('ccw_graph');
SELECT name FROM ag_graph ORDER BY name;
