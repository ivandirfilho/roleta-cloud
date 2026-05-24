# S14 — Adoption Playbook

Roadmap para promover features S7-S13 de "dev only" para "prod default".

## Fases

### F0 — Dev Only (estado atual)
- Codigo merged em main, todas as flags off.
- Tests unitarios passando.

### F1 — Internal Shadow
- Ativar `strategy_shadow_predictor` em 100% das decisoes.
- Sem efeito em decisao real; apenas log.
- Duracao: 7 dias minimo.
- Saida: relatorio de divergencia, latencia, taxa de erro.

### F2 — Canary 5%
- Ativar nova estrategia para 5% das decisoes via `pct=5`.
- Monitorar gates do S13.
- Duracao: 48h.

### F3 — Ramp 25 -> 50 -> 100
- Aumentar `pct` em saltos de 25%, intervalo minimo 1h.
- Pausar imediatamente se win_rate cair > 2pp.

### F4 — Default On
- Setar `pct=100`, `enabled=true` como default da migration.
- Codigo legado removido na release seguinte (`vN+1`).

## Checklist por feature

- [ ] Tests unitarios verdes
- [ ] Documentacao em `docs/runbooks/<feature>.md`
- [ ] Feature flag em `shared.feature_flags` com seed
- [ ] Metric em Sx-OBS (Grafana)
- [ ] Runbook de rollback (1 comando SQL)
- [ ] Owner identificado

## Rollback

Sempre 1-comando:
```sql
UPDATE shared.feature_flags SET enabled=false WHERE name='<flag>';
```
Cache de 30s no app => efeito em <=30s.
