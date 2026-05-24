# Política de Pausa Controlada — Sx-PAUSE

Sprint `Sx-PAUSE` do `plano_implentacao_pos_sessao_24_05.md`.

Quando o operador precisa **parar o app sem perder dados em voo** (deploy
sensível, troca de schema, migration de produção, hotfix arriscado).

---

## Quando pausar

| Situação | Pausa obrigatória? |
|---|---|
| Migration Alembic que altera tabela ativa | ✅ Sim |
| Deploy de hotfix com mudança de schema | ✅ Sim |
| Restore de backup do PG | ✅ Sim |
| Mudança de feature flag (canário) | ❌ Não — flag é hot-reload |
| Deploy de patch app sem mudança de schema | ❌ Não — workflow já gracefully restart |
| Tuning kernel/sysctl | ❌ Não |

---

## Procedimento

### 1. Anunciar (T-5min)

Sinalizar nos canais do operador que vai entrar em janela de manutenção.
A sessão atual continua até o próximo idle.

### 2. Drenar (T-2min)

```bash
ssh root@187.45.181.75 bash /root/roleta-cloud/scripts/pause_app.sh
```

O script:
1. Marca feature flag `app_paused=true` no PG (`shared.feature_flags`)
2. Aguarda 60s para clientes WS naturalmente desconectarem
3. Loga estado atual em `/root/roleta-cloud/data/pause-<timestamp>.json`
4. Para o container `roleta-cloud` (não o `roleta-pg`)

### 3. Janela de manutenção

Executar a operação sensível. Container PG continua disponível para
migrations/queries diretas.

### 4. Resumir

```bash
ssh root@187.45.181.75 bash /root/roleta-cloud/scripts/resume_app.sh
```

O script:
1. Sobe `docker compose up -d` (re-create se necessário)
2. Aguarda healthcheck (timeout 90s)
3. Marca `app_paused=false` no PG
4. Verifica logs por 30s em busca de `ERROR|FATAL`
5. Retorna exit 0 só se tudo limpo

### 5. Validar

- `curl -I https://roleta.xma-ia.com` → 200
- `docker logs roleta-cloud --tail 20 | grep -iE "error|fatal"` → vazio
- Painel/cliente: receber novo spin em até 10s

---

## RTO esperado

| Etapa | Duração |
|---|---|
| Drenar | 60s |
| Janela média | 2-10 min |
| Resumir + valida | 90-120s |
| **Total** | ~5-15 min |

---

## Fallback (script falhou)

Pausa manual:
```bash
docker stop roleta-cloud
# ... fazer trabalho ...
docker start roleta-cloud
docker logs roleta-cloud --tail 50
```

PG fica sempre up — composes separados (vide `docker-compose.pg.yml` vs `docker-compose.yml`).
