# S9 — Tuning ivfflat (pgvector)

## Quando

Indice `cw.spins_vectors_ivfflat` e `ccw.spins_vectors_ivfflat` foram
criados com `lists = 100` (migration 0003). Isso eh otimo ate ~10k rows
por schema. Acima disso a regra de bolso eh:

```
lists ≈ sqrt(N)   onde N = num_rows da tabela
```

| N (rows)   | lists recomendado | probes (consulta) |
|------------|-------------------|-------------------|
| 1k         | 32                | 1-4               |
| 10k        | 100  ← atual      | 4-10              |
| 100k       | 316               | 10-20             |
| 1M         | 1000              | 20-40             |

`probes` eh setado por sessao: `SET ivfflat.probes = 10;` antes do SELECT.

## Procedimento (zero-downtime)

Por schema (cw / ccw), rodar em janela de baixo trafego:

```sql
-- 1. Calcular tamanho atual
SELECT count(*) FROM cw.spins_vectors WHERE compressed_vector IS NOT NULL;

-- 2. Criar novo indice CONCURRENTLY com lists ajustado
CREATE INDEX CONCURRENTLY spins_vectors_ivfflat_v2
ON cw.spins_vectors USING ivfflat (compressed_vector vector_l2_ops)
WITH (lists = 316);

-- 3. Validar (deve fazer scan do novo)
SET ivfflat.probes = 15;
EXPLAIN ANALYZE
SELECT id FROM cw.spins_vectors
ORDER BY compressed_vector <-> '[0.1,0.2,0.3,0.4]'::vector
LIMIT 10;

-- 4. Trocar o nome (atomico)
BEGIN;
ALTER INDEX cw.spins_vectors_ivfflat RENAME TO spins_vectors_ivfflat_old;
ALTER INDEX cw.spins_vectors_ivfflat_v2 RENAME TO spins_vectors_ivfflat;
COMMIT;

-- 5. Drop antigo apos 1h de observacao
DROP INDEX CONCURRENTLY cw.spins_vectors_ivfflat_old;
```

## Recall vs Speed

- `lists` maior  -> menor recall, mais rapido.
- `probes` maior -> maior recall, mais lento.
- Default seguro: `probes = lists / 10`.

## Monitoramento

Adicionar ao Grafana (Sx-OBS):
- `pg_stat_user_indexes.idx_scan` em `spins_vectors_ivfflat`
- Latencia p95 de queries com `<->` operator
- Tamanho do indice (`pg_relation_size`)

## Quando NAO usar ivfflat

- N < 1k rows: scan sequencial eh mais rapido.
- Recall critico (>99%): considere `hnsw` (pgvector >= 0.5).
