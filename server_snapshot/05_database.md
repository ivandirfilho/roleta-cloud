# PostgreSQL (roleta-pg)

- versao: 15.18 (Debian 15.18-1.pgdg12+1)
- database: roleta
- tamanho: 13 MB
- extensoes: plpgsql, vector, age, pgcrypto, pg_stat_statements

## Tabelas por volume (n_live_tup)
```
shared.outbox = 5
ccw.spins_vectors = 3
cw.spins_vectors = 2
shared.strategy_versions = 0
ag_catalog.ag_label = 0
shared.feature_flags = 0
cw_graph._ag_label_vertex = 0
cw.spin_features = 0
ccw_graph._ag_label_edge = 0
ag_catalog.ag_graph = 0
ccw_graph._ag_label_vertex = 0
ccw.spin_features = 0
cw_graph._ag_label_edge = 0
shared.alembic_version = 0
```

## Outbox (CDC) por status
```
processed = 2706
```

## Outbox failed por event_type
```
nenhum
```

## Ultimo evento outbox
```
2026-06-10 18:51:09.081719+00
```

## Alembic version
```
0006_spin_features
```
## Estatisticas de dominio
```
spins_total = tabela inexistente
spins_ultimo = tabela inexistente
decisions_total = tabela inexistente
decisions_ultimo = tabela inexistente
calibration_fill = tabela inexistente
sessions_total = tabela inexistente
dna_events = tabela inexistente
spin_embeddings = tabela inexistente
```
