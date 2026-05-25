# estrutura_atual_24.md — Estado real Roleta Cloud (snapshot 2026-05-24 21:16 BRT / 2026-05-25 00:16Z)

> **Stack MCP usada**: graphify (mapa do código), filesystem (leitura local), brave-search (não necessária no escopo final), sequential-thinking (análise do funil de decisão), memory (registro de entidades `RoletaCloud_Estrutura_24_05`, `Resultados_Live_HoraAtual`).

---

## 0. TL;DR — o que está acontecendo agora

| Indicador (última 1h) | Valor | Status |
|---|---|---|
| Decisões processadas | 260 | ✅ |
| Apostas (`APOSTAR`) | 248 (95%) | ⚠️ alto demais |
| Hits | 107 | — |
| Misses | 120 | — |
| **Acc apostas** | **43.1%** | 🔴 **abaixo do break-even (47.2%)** |
| Outbox PG pending | 0 (67 processadas) | ✅ |
| CDC LISTEN state | 1 (ativo) | ✅ |
| Reconnects LISTEN | 1 (fix S-OBS validado) | ✅ |
| Sessões abertas / hora | 3 (turnover 13-16 min) | ⚠️ |
| Max gale alcançado | sempre 1 | 🔴 desperdiça streaks |

**Veredito**: infraestrutura sólida e observável. Estratégia **não está rentável** na janela atual — está 4 pp abaixo do break-even teórico do modelo (47.2%). Há gargalos claros tanto no kill-switch quanto na escalação Martingale e no ramo M02-Sigmoid drift até offset=13.

---

## 1. Infraestrutura — engenharia reversa (servidor Debian 187.45.181.75)

### 1.1 Containers em execução (`docker ps`)

| Container | Imagem / função | Health | Porta |
|---|---|---|---|
| `roleta-cloud` | App principal Python — `main.py`, recebe spins via WebSocket de extractor, processa via `GameEngine`, grava SQLite + outbox PG | healthy | 8766 (health) |
| `roleta-pg` | Postgres 16 com schema `shared.outbox` + função/trigger `outbox_notify` | healthy | 5432 (interno) |
| `roleta-cdc-worker` | Worker Python que faz LISTEN no canal `outbox_new`, lê outbox e propaga para tabelas finais | healthy | **8767 (/metrics novo S-OBS-2)** |
| `pg-exporter` | postgres_exporter para métricas PG | up | 9187 |
| `node-exporter` | métricas host | up | 9100 |

### 1.2 Observabilidade

- `grafana-agent` (host) raspa 4 jobs: `postgres`, `roleta-cloud`, `node`, `cdc-worker` → todos `up` validado nesta sessão.
- Métricas CDC novas (commit `ebf78d1`):
  - `cdc_notify_received_total` = 6
  - `cdc_notify_wakeups_total` = 6
  - `cdc_batch_events_processed_total` = 6
  - `cdc_listen_reconnect_total` = 1 (validado após `restart postgres`)
  - `cdc_listen_state` = 1 (LISTEN ativo)
- Logs Docker JSON → Loki (`logs-prod-024.grafana.net`).

### 1.3 Persistência

- **SQLite** (named volume `roleta-cloud_roleta-data` → `/app/data/decisions.db`):
  - `sessions` — agregação por sessão de jogo (id, start/end_time, totals).
  - `decisions` — 1 linha por spin processado. **Schema com 30+ colunas** incluindo: `tr_*` (Triple Rate), `sda_*` (estratégia SDA17), `gale_*` (Martingale), `result_*` (hit/actual), `sda_offset`, `sda_offset_type` (introduzidos na v4.3).
  - `gale_windows` — janelas de Martingale (started_at/ended_at, hits/plays, result).
  - `window_plays` — cada play de uma janela individualmente.
- **PostgreSQL** (`shared.outbox`):
  - Trigger `outbox_notify` → `pg_notify('outbox_new', ...)` (alembic head: **`0005_outbox_notify`** após esta sessão).
  - 67 eventos propagados na última hora, 0 pendentes.
- **Backup** (S-BAK-1 desta sessão):
  - `wal-g v3.0.5` em `/root/roleta-cloud/wal-g/wal-g` (bind no compose).
  - `archive_command = wal-g wal-push` no postgresql.conf (PG já configurado).
  - Cron `/etc/cron.d/walg-backup` 02:00 UTC daily → B2.
  - 3 backups visíveis em `wal-g backup-list`, último: `base_000000010000000000000020`.

### 1.4 Topologia de dados (sintética)

```
Extractor (browser/ext) ── WebSocket ──► roleta-cloud (server/message_handler.py)
                                              │
                                              ├─► core/engine.GameEngine.process_spin
                                              │     ├─► strategies/sda17.M15-ADA analyze
                                              │     ├─► state/bet_advisor.TripleRateAdvisor (kill switch)
                                              │     └─► state/game.MartingaleState.get_gale
                                              │
                                              ├─► SQLite /app/data/decisions.db (decisions, gale_windows…)
                                              │
                                              └─► PostgreSQL shared.outbox (dual-write)
                                                       │  trigger pg_notify('outbox_new')
                                                       ▼
                                            roleta-cdc-worker  ── tabelas finais (shared.*)
                                                       │
                                                       └─► /metrics :8767 ─► grafana-agent ─► Grafana Cloud
```

---

## 2. Lógica de decisão — como uma jogada vira aposta

Pipeline em `core/engine.GameEngine.process_spin` (recorte real, `core/engine.py:53-172`):

1. **Verifica predição anterior** (`game_state.check_prediction(numero)` → `hit_result`).
2. **Atualiza Martingale** da direção que apostou (`MartingaleState.update`):
   - HIT: `consecutive_hits++`. Se estava em G3 e HIT → **take-profit**, força reset G1.
   - MISS: `consecutive_hits=0`, level=1.
   - Streak global cross-direction também é atualizado (`global_consecutive_hits`).
3. **Processa spin** no `game_state` (timeline + força calculada).
4. **Atualiza estado adaptativo** da estratégia (`strategy.update_adaptive(...)`) — feedback do erro para o `_sigmoid_off` (M02-PctSigmoid).
5. **Análise SDA-17** (`strategies/sda17.SDA17Strategy.analyze`):
   - Janela adaptativa 7→5→3→2 forças.
   - IQR outlier rejection (statistics.quantiles).
   - Weighted median com decay 0.8 (peso exp. nas mais recentes).
   - Drift detection.
   - **Triple Focus 17 números** = C1 (raio 3, 7 num) + C2 (raio 2, 5 num) + C3 (raio 2, 5 num).
   - Offsets C2/C3 controlados por **sigmoid dampened feedback** (max ±2 posições/jogada). Faixa `OFFSET_MIN=7 .. OFFSET_MAX=13`, prior em 10.
6. **Triple Rate Advisor / Kill Switch** (`state/bet_advisor.py:32-117`):
   - Calcula `c4`, `m6`, `l12` rates.
   - **Único critério de PULAR**: `len(perf)>=4 AND c4==0 AND sda_score<=2`. Tudo o mais é APOSTAR.
   - Define confidence (alta/media/baixa) só para display.
7. **Decisão final**:
   - SDA suficiente → APOSTAR com os 17 números.
   - SDA insuficiente mas timeline>0 → **APOSTAR fallback G1 seguro** (raio 10 ao redor de `last_number`).
   - Timeline vazia → PULAR.
8. **`MartingaleState.get_gale(score, c4_rate, confidence)`** define G1/G2/G3:
   - `confidence=="alta"` ⇒ `max_gale=1`.
   - `confidence=="baixa"` ⇒ `max_gale=1`.
   - `c4_rate<0.15` ⇒ `max_gale=1`.
   - Caso contrário, escalação por streak global (≥2 → G2, ≥3 → G3).

---

## 3. Engenharia reversa das jogadas reais (última hora — sample)

Amostra das 15 últimas decisões (top do `LAST_HOUR_DECISIONS`):

| id | hora | spin | act | sda_sc | g | hit | actual | sigmoid_off |
|---|---|---|---|---|---|---|---|---|
| 3834 | 00:16:31 | 7 | APOSTAR | 4 | 1 | (pendente) | — | 9 |
| 3833 | 00:15:43 | 8 | APOSTAR | 4 | 1 | 0 | 7 | 10 |
| 3832 | 00:14:57 | 5 | APOSTAR | 4 | 1 | 0 | 8 | 10 |
| 3831 | 00:14:07 | 21 | APOSTAR | 4 | 1 | 0 | 5 | 10 |
| 3830 | 00:13:21 | 19 | APOSTAR | 4 | 1 | 1 | 21 | 11 |
| 3829 | 00:12:31 | 17 | APOSTAR | 6 | 1 | 0 | 19 | 10 |

**O que isso conta:**
- Sequência 3829→3832 é **3 misses consecutivos** com `sda_score=4` (sinal médio-bom) e offset_sigmoid girando 10→11→10. O modelo perdeu padrão e o sigmoid começou a "tremer" (oscila 9-12 dentro de 4 jogadas).
- `sda_score=6` (3829) e ainda assim miss → score alto **não preditivo** quando sigmoid_off está deslocado.
- A 3830 hit isolado (G1) reseta nada porque já estava em G1 → não há propagação de ganho.

### 3.1 Performance por offset adaptativo

```
sigmoid_off | n  | hits | acc
------------|----|------|------
9           |  3 |  1   | 33%   (warm-up)
10          | 62 | 31   | 50.0% ✅
11          | 41 | 20   | 48.8% ✅
12          | 61 | 31   | 50.8% ✅
13          | 69 | 24   | 34.8% 🔴
"" (off=0)  | 12 |  0   | 0%   (fallback early-session)
```

**Bug óbvio**: o controlador sigmoid passa **muito tempo** em `offset=13` (69 plays = 27% das apostas) e justamente lá a estratégia falha. Isto é um **drift contra-otimal** — o feedback positivo do sigmoid não está penalizando suficientemente quando o offset cresce além do prior 10-12.

### 3.2 Performance por gale_level

```
G1: 235 plays / 101 hits (43.0%)
G2:   8 plays /   4 hits (50.0%)
G3:   5 plays /   2 hits (40.0%)
```

**Bug estrutural**: das 248 apostas, **94.7% ficaram em G1**. A regra `confidence=="alta" ⇒ max_gale=1` (`state/game.py:60`) está **prendendo o sistema em G1**, porque a maioria das predições do Triple Rate é "alta" ou "media-alta". O Martingale anti-streak existe mas não consegue escalar.

### 3.3 Sessões / turnover

```
86b67a4b              start 00:08:28  end (open)        spins=10 bets=8 hits=1
session_1779666919452 start 23:55:19  end 00:08:00      spins=11 bets=9 hits=4
77ef4475              start 23:39:18  end 23:55:19      spins=23 bets=22 hits=11
```

3 sessões na última hora, turnover médio ~15 min. O `_id` muda de formato (UUID curto vs `session_<epoch_ms>`) entre sessões — possível inconsistência no factory de session_id.

---

## 4. A estratégia projetada para hoje **está funcionando**?

| Critério projetado | Realidade última hora | Status |
|---|---|---|
| Cobertura 17 números (45.9%) | mantida | ✅ |
| Break-even 47.2% | 43.1% real | ❌ **−4.1 pp** |
| CW ~54% / CCW ~46% (simulação) | combined 43% (precisa drilldown por direção) | ❌ |
| Martingale Anti-Streak G1→G2→G3 | 95% preso em G1 | ❌ |
| Kill Switch protege em catástrofe | dispara só com timeline vazia | ⚠️ inerte |
| Sigmoid converge para offset ótimo | drift para offset=13 (pior) | ❌ |
| CDC dual-write SQLite↔PG | 100% processado | ✅ |
| Observabilidade (Prom + Loki) | 4 targets up + metrics CDC | ✅ |

---

## 5. Auditoria profunda — bugs e melhorias detectados

### BUG-EST-1 (crítico) — drift sigmoid → offset=13
- Local: `strategies/sda17.SDA17Strategy.update_adaptive` (controlador M02-PctSigmoid).
- Evidência: 69/248 apostas (27%) em offset=13 com 34.8% acc; offsets 10-12 (vizinhança do prior) entregam ≥48%.
- Hipótese: `SIGMOID_K=6` + `SIGMOID_SCALE=2.0` com `MISS_CROSS_RATE=0.3` não freia a deriva quando o erro é assimétrico (mais erros para mesma direção empurram offset sempre num sentido).
- Impacto: −15 pp acc nas 69 apostas afetadas = aproximadamente 10 hits perdidos/hora.

### BUG-EST-2 (alto) — Martingale preso em G1 por `confidence==alta`
- Local: `state/game.MartingaleState.get_gale:54-78`.
- Evidência: 94.7% das apostas em G1. Regra `confidence=="alta" → max_gale=1` impede escalação justamente quando temos sinal forte.
- Hipótese: regra original era proteção contra **spike regression**, mas o Triple Rate Advisor v2 raramente devolve "baixa"; "alta" se tornou o caso comum, não excepcional.
- Impacto: bloqueio sistemático do upside do Anti-Martingale.

### BUG-EST-3 (alto) — Kill switch inerte
- Local: `state/bet_advisor.TripleRateAdvisor.analyze:78-91`.
- Evidência: dos 260 spins, 248 APOSTAR + 12 PULAR (todos por timeline vazia inicial). Critério `c4==0 AND sda_score<=2` praticamente nunca é satisfeito porque o SDA quase sempre devolve score≥3.
- Impacto: sistema aposta mesmo em janelas claramente ruins (3 misses seguidos não criam pause).

### BUG-EST-4 (médio) — Fallback G1 seguro com 0% acc
- Local: `core/engine.py:129-144` (ramo `should_bet=False` → APOSTAR fallback).
- Evidência: 12 jogadas com `sda_offset_type=""` (não-sigmoid) → 0 hits.
- Impacto: 12 misses garantidos por hora de sessão recém-criada × 3 sessões/hora = ~36 misses estruturais.

### BUG-EST-5 (médio) — Sessão rotacionando a cada ~15 min
- Local: `server/message_handler.py` (lógica de criação de session_id).
- Evidência: 3 sessões em 60 min; IDs com formatos diferentes (`86b67a4b` vs `session_1779666919452`).
- Impacto: Martingale e estado adaptativo do SDA são **resetados** a cada nova sessão → cada sessão começa do warmup (`min_forces=2`) perdendo aprendizado.

### BUG-OBS-1 (baixo) — Falta alert rule para `cdc_listen_state==0`
- Adicionado nas sprints; sem regra atual, queda silenciosa do canal LISTEN só seria notada via degradação.

### MEL-1 (alto) — Persistir `_sigmoid_off` e `_recent_hits` entre sessões
- Estado adaptativo das estratégias é volátil ao restart de sessão; deveria persistir em `state.json` (ou tabela) por direção.

### MEL-2 (alto) — Penalizar offsets nos extremos da banda (`7` ou `13`)
- Modificar M02-PctSigmoid para adicionar termo de regularização que **puxa de volta** se o offset passar de uma janela perto do prior (10±2). Por exemplo: `HIT_TIGHTEN = 0.16` quando `|off − 10| > 2`.

### MEL-3 (médio) — Kill switch v3 baseado em **rolling acc < break_even − margem** em janela curta
- Em vez de `c4==0`, usar `c4 < 0.30 AND sda_score < 4` para pausar 1-2 spins.

### MEL-4 (médio) — Take-profit fora do G3
- Atualmente `take_profit` só dispara em `G3 HIT`; estender para G2 quando streak global ≥ 3.

### MEL-5 (baixo) — Endpoint `/health/full` ou `/api/status` com snapshot estratégia (offsets, streak, last 10 acc)
- App responde só com `roleta-cloud health server` em `/` e `{"status":"ok"...}` em `/health`. Sem introspecção viva.

### MEL-6 (baixo) — Padronizar `session_id` (escolher entre UUID e `session_<epoch>`)
- Atualmente convivem dois formatos no mesmo banco.

### MEL-7 (médio) — Dashboard Grafana CDC + Strategy
- Pendente da S-OBS-2 (commits `ebf78d1`/`6fe7cce`): painéis para os 5 novos counters + acc rolling por direção/offset.

### MEL-8 (médio) — Alert rules
- `cdc_listen_state == 0 for 5m` (crítico).
- `rate(cdc_listen_reconnect_total[15m]) > 0.1` (warning).
- `acc_rolling_30min < 0.42` (warning sobre rentabilidade).

---

## 6. Próximas sprints (pós-auditoria)

> Premissa: testar com janela de 30 min de produção real (operador validou em sessões anteriores). Nenhuma sprint mexe em SSH/credenciais/firewall.

### Sprint S-STRAT-1 — Anti-drift sigmoid (BUG-EST-1)
**O quê**: Ajustar `strategies/sda17.py` para penalizar offsets fora da faixa [9, 12].
**Como**:
1. Adicionar constante `OFFSET_REGULARIZER_BAND = (9, 12)` e `OFFSET_REGULARIZER_RATE = 0.20`.
2. Em `update_adaptive`, após cálculo do novo `_sigmoid_off[dir]`, se sair da banda aplicar pull-back: `off += sign(10 - off) * REG_RATE`.
3. Tracking métrica `cdc_strategy_offset` (Gauge por dir) exportada via novo endpoint do app principal (não do cdc-worker).
**Por quê**: 27% das apostas em offset=13 com 34.8% acc derrubam acc geral em ~4 pp. Esta correção isolada deve levar acc para ~47-48% (break-even).

### Sprint S-STRAT-2 — Martingale escalável com sinal forte (BUG-EST-2)
**O quê**: Reescrever `MartingaleState.get_gale`.
**Como**:
1. Remover bloqueio `confidence=="alta" → max_gale=1`.
2. Substituir por: `if c4_rate < 0.25 OR sda_score < 3: max_gale=1`.
3. Manter regra existente para `confidence=="baixa"`.
4. Adicionar canary: log estruturado `mg_gale_decided` com `desired/applied/reason`.
**Por quê**: hoje 94.7% das apostas viram G1 mesmo quando há streak global ≥ 2. Liberando G2 com sinal forte recupera upside do Anti-Martingale.

### Sprint S-STRAT-3 — Kill switch v3 e PULAR adaptativo (BUG-EST-3)
**O quê**: Critério mais agressivo no `TripleRateAdvisor`.
**Como**:
1. Novo critério PULAR: `c4 < 0.30 AND sda_score < 4` (em vez de `c4==0`).
2. Adicionar cooldown: se PULAR, segurar por 1 spin antes de reavaliar.
3. Métrica `cdc_advisor_pulls_total`.
**Por quê**: hoje só pulamos em timeline vazia. Cobrir caso "3 misses seguidos com sinal médio" evita streaks de perda.

### Sprint S-STRAT-4 — Persistir estado adaptativo entre sessões (BUG-EST-5 + MEL-1)
**O quê**: salvar `_sigmoid_off`, `_recent_hits`, `_cooldown`, `_drift_freeze`, `_mg_resets` por direção em `state.json` e recarregar em init da estratégia.
**Como**:
1. Estender `state/game.GameState.save()` para incluir `strategy.get_adaptive_state()`.
2. Em `__init__` do GameState, se `state.json` tiver `strategy_state`, chamar `strategy.load_adaptive_state(...)`.
3. Versionar com `strategy_state_version` (rejeitar incompatíveis).
**Por quê**: cada nova sessão hoje reseta aprendizado → 12 misses garantidos (fallback) × 3 sessões/h = ~36 misses estruturais.

### Sprint S-OBS-3 — Endpoint `/api/strategy` + Dashboard Grafana (MEL-5 + MEL-7)
**O quê**: expor introspecção viva da estratégia (offsets, streak, acc rolling) + dashboard.
**Como**:
1. Adicionar em `server/health_server.py` rota `/api/strategy` retornando JSON com: `sigmoid_off por direção`, `consecutive_hits`, `global_streak`, `acc_30min_por_offset`, `last_10_decisions`.
2. Exportar Counters/Gauges: `cdc_strategy_acc_30min`, `cdc_strategy_offset{dir}`, `cdc_strategy_gale_distribution{level}`.
3. Subir dashboard Grafana JSON em `docs/grafana/strategy.json`.
**Por quê**: hoje não temos visão tempo real da saúde da estratégia; toda análise é forense via SQLite.

### Sprint S-OBS-4 — Alert rules (MEL-8)
**O quê**: criar alertas no Grafana Cloud (manual no portal + arquivo `docs/grafana/alerts.yml` no repo).
**Como**:
1. `cdc_listen_state == 0 for 5m` (severity critical).
2. `rate(cdc_listen_reconnect_total[15m]) > 0.1` (severity warning).
3. `cdc_strategy_acc_30min < 0.42 for 30m` (warning).
4. `(sum(rate(decisions_total[10m])) by () ) == 0 for 5m` (critical — sem spins).
**Por quê**: degradações silenciosas só sendo notadas no fim do dia hoje.

### Sprint S-MIG-2 — Padronizar session_id (MEL-6)
**O quê**: forçar `session_id = uuid4().hex[:8]` em todos os pontos.
**Como**: refactor pontual em `server/message_handler.py`. Migration leve para anotar formato legado.
**Por quê**: convivência de 2 formatos quebra agregações futuras.

### Sprint S-WALG-1 — Restore drill em ambiente isolado
**O quê**: validar que `wal-g backup-fetch` funciona em container PG zerado.
**Como**: script `scripts/walg-restore-drill.sh` + container scratch `roleta-pg-drill`.
**Por quê**: backup sem drill é placebo. Pendente da S-BAK-1.

---

## 7. Priorização sugerida (próxima sessão)

1. **S-STRAT-1** (anti-drift sigmoid) — maior impacto/menor risco, ~30 min.
2. **S-STRAT-2** (Martingale escalável) — alto impacto, requer canary.
3. **S-STRAT-4** (persistir estado) — bloqueia ganho de S-STRAT-1/2 se reset a cada sessão.
4. **S-OBS-3** + **S-OBS-4** — para medir efeito real das mudanças acima.
5. **S-STRAT-3**, **S-MIG-2**, **S-WALG-1** — qualidade e robustez.

---

## 8. Apêndice — comandos de inspeção live usados

```bash
# Estado containers
ssh root@SRV 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Health app + CDC metrics
curl -s http://localhost:8766/health
curl -s http://127.0.0.1:8767/metrics | grep -E "^cdc_"

# Decisões última hora
docker exec roleta-cloud sqlite3 -header -column /app/data/decisions.db \
  "SELECT id, time(timestamp) t, spin_number sn, final_action act, sda_score sc, \
          gale_level g, result_hit hit, result_actual ra, sda_offset off, sda_offset_type oft \
   FROM decisions WHERE timestamp >= datetime('now','-1 hour') ORDER BY id DESC LIMIT 40;"

# Sumário acc última hora
docker exec roleta-cloud sqlite3 /app/data/decisions.db \
  "SELECT COUNT(*) total, \
          SUM(CASE WHEN final_action='APOSTAR' THEN 1 ELSE 0 END) apostas, \
          SUM(CASE WHEN final_action='APOSTAR' AND result_hit=1 THEN 1 ELSE 0 END) hits \
   FROM decisions WHERE timestamp >= datetime('now','-1 hour');"

# Outbox
docker exec roleta-pg psql -U roleta -d roleta -c \
  "SELECT COUNT(*) FILTER (WHERE processed_at IS NULL) pending, \
          COUNT(*) FILTER (WHERE processed_at IS NOT NULL) processed \
   FROM shared.outbox WHERE created_at >= now() - interval '1 hour';"
```

---

**FIM do documento.** Auditoria fechada, 11 issues catalogados (5 BUG + 8 MEL), 7 sprints propostas, ordem de execução recomendada. Decisão do operador de não tocar SSH/credenciais permanece respeitada.
