# Runbook — Rollback de qualquer Sprint

Sprint `Sx-ROLL` do plano `plano_implentacao_pos_sessao_24_05.md`.

Cada sprint tem um caminho de reversão garantido. Este documento centraliza.

---

## Convenções

- Toda mudança de aplicação entra em produção via **tag git `v*`** que dispara `.github/workflows/deploy.yml`
- O servidor mantém os últimos 5 backups de banco em `/root/roleta-cloud/data/*.bak.*` e basebackups remotos via WAL-G (S4-BAK)
- Stack PG roda em compose separado (`docker-compose.pg.yml`); rolar back o app **não** derruba o PG e vice-versa

---

## Rollback por Sprint

### S0 — Quick Wins v4.4

| Evento | Comando |
|---|---|
| Erro pós-deploy v4.4.0 | `git tag v4.3.3-rollback 6bdde3c && git push origin v4.3.3-rollback` |
| Validar | `ssh root@... 'docker exec roleta-cloud cat VERSION'` deve mostrar 4.3.x |
| RTO | ~2 min (build + restart) |
| Dados perdidos | 0 (banco preservado) |

### S0.5 — postgres-stack imagem

| Evento | Comando |
|---|---|
| Build quebra ou imagem ruim | `docker rmi roleta/postgres-stack:pg15-age15` + revert do commit `914b79a` |
| Dev local quebra | `docker compose -f docker-compose.dev.yml down -v` |
| Servidor não afetado | Imagem só existe local até S4 |

### S4 — postgres-stack em produção (Debian)

| Evento | Comando |
|---|---|
| Container PG não sobe | `cd /root/roleta-cloud && docker compose -f docker-compose.pg.yml down` |
| Volume corrompido | `docker compose -f docker-compose.pg.yml down -v` (DESTRÓI dados) — só se sem dual-write ativo |
| App roleta-cloud intocado | Sempre — compose separado |
| RTO | <1 min |

### S5 — Outbox dual-write

| Evento | Comando |
|---|---|
| PG offline → outbox enche | Worker pula automaticamente; app continua escrevendo em SQLite |
| Worker bugado | `docker compose stop cdc_worker` |
| Reverter código | `git revert` commit de S5 + tag patch + deploy |
| Replay manual | `python scripts/cdc_replay.py --from-uuid <X>` |

### S6–S10 — pgvector / autoencoder / AGE / outlier / cold

| Evento | Comando |
|---|---|
| Query lenta | Drop index suspeito; analisar `pg_stat_statements` |
| Modelo AE ruim | `cp models/ae_cw_<last_good>.joblib models/ae_cw_active.joblib` |
| Feature flag | `UPDATE shared.feature_flags SET enabled=false WHERE name='cold_regions'` |

### S11 — Shadow predictor

| Evento | Comando |
|---|---|
| Shadow trava | Circuit breaker abre automaticamente após 5 falhas/60s |
| Latência alta | Reduzir `SHADOW_TIMEOUT_MS=500` em env e reiniciar |
| Desligar shadow | `UPDATE shared.feature_flags SET enabled=false WHERE name='shadow_predictor'` |

### S13 — Canário 10→50%

| Evento | Comando |
|---|---|
| Métricas pioram | `UPDATE shared.feature_flags SET pct=0 WHERE name='new_decision_engine'` |
| Volta instantânea | <1s (próxima decisão já lê flag) |

### S14 — Adoption v5.0.0

| Evento | Comando |
|---|---|
| Rollback completo | `git tag v4.4.99-rollback v4.4.0 && git push origin v4.4.99-rollback` |
| Manter PG/dados | `git revert` apenas os commits de S14, deploy nova tag |

---

## Procedimento Genérico de Emergência

1. **Avaliar gravidade** (≤30s)
   - Site responde? `curl -I https://roleta.xma-ia.com`
   - Container healthy? `docker ps`
   - Banco íntegro? `docker exec roleta-cloud sqlite3 data/decisions.db 'SELECT COUNT(*) FROM spins'`

2. **Decidir rollback vs hotfix** (≤2 min)
   - Bug claro e localizado → hotfix em branch + PR + tag patch
   - Comportamento errático ou múltiplos sintomas → rollback para última tag estável conhecida

3. **Rollback de aplicação** (≤5 min)
   ```bash
   ssh root@187.45.181.75 'cd /root/roleta-cloud && git fetch --tags && git checkout <tag_anterior> && docker compose build && docker compose up -d'
   ```

4. **Validação pós-rollback** (≤2 min)
   - `docker logs roleta-cloud --tail 50 | grep -iE "error|fatal"` deve ser vazio
   - Endpoint público deve retornar HTTP 200
   - Container healthy
   - Métricas Grafana voltaram ao baseline em até 5 min

5. **Post-mortem** (≤24h)
   - Criar issue GitHub com root cause
   - Atualizar checklist da sprint culpada
   - Atualizar este runbook se o procedimento falhou em algum passo

---

## Contatos / Acessos

- VPS: `root@187.45.181.75` (chave SSH em `~/.ssh/id_rsa` Windows)
- GitHub Actions Secrets: `SERVER_HOST`, `SERVER_USER`, `SERVER_PORT`, `SSH_PRIVATE_KEY`
- Repo: https://github.com/ivandirfilho/roleta-cloud
- Tag estável atual: **v4.4.0** (deployada 2026-05-24)
