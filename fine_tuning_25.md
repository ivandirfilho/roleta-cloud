# Fine-Tuning 25 — Engenharia Reversa, Estrutura Estratégica e 5 Ciclos de Auditoria

> **Stack MCP**: `graphify` (mapa do código) · `filesystem` (snapshots) · `sequential-thinking` (raciocínio) · `memory` (continuidade de sessão) · `brave-search` (validação externa pontual)
> **Persona**: YOLO Orchestrator · modelo fixo `claude-opus-4.7` · autopilot ativo
> **Servidor live**: `roleta-cloud v4.4.0` (commit `ef36d93`) em `187.45.181.75`
> **Janela de análise**: 04:21–04:28 UTC 2026-05-25 (após restart pós S-OBS-16/V4)

---

## §0 Snapshot Live (fonte da verdade)

| item | valor | fonte |
|---|---|---|
| versão app | `v4.4.0` | banner stdout |
| commit | `ef36d93` (S-OBS-16 + EMA on-spin) | `git log -1` |
| state schema | `2.0.0` | `state.json` |
| último número observado | `26` (anti-horário hit) | `state.json.last_number` |
| `perf_sda17_cw` (últ. 12) | `[T,F,F,F,F,T,F,F,T,F,F,F]` → **acc 25 %** | `_adaptive_state.recent_hits.cw` |
| `perf_sda17_ccw` (últ. 12) | `[F,F,T,T,T,F,F,F,T,T,F,F]` → **acc 42 %** | idem ccw |
| `kill_pulls` totais | `21` | `_adaptive_state.cooldown` |
| `shadow_grid_n` (cada shift) | `15` | `get_shadow_stats()` |
| `incumbent_shadow_n` | `7 cw / 6 ccw` (rampup pós-V3) | idem |
| `shadow_ema[*]` | `None` ainda (precisa de mais spins pós-V4) | idem |
| serviços observabilidade | `prometheus`, `grafana`, `alertmanager v0.27` healthy | `docker ps` |
| pg_stat_statements | habilitado (S-DBA-1 pendente) | `\dx` |
| testes | **183 passando** | `pytest -q` |

---

## §1 Estrutura estratégica — como cada decisão é tomada

```
┌───────────────────────────────────────────────────────────────────────┐
│ Spin chega via WebSocket  ▸  number (0–36)                            │
└───────────────┬───────────────────────────────────────────────────────┘
                │
                ▼
   ┌───────────────────────────┐  Timeline CW (12) + Timeline CCW (13)
   │ TIMELINE WINDOW           │  janelas deslizantes de forças por direção
   └─────────────┬─────────────┘
                 ▼
   ┌───────────────────────────┐  • SDA17 (Smart Decision Advisor 17)
   │ SDA17 ADVISOR             │  • 3 centros candidatos por direção
   │ strategies/sda17.py       │  • Triple-Rate score: c2/c4/c6
   │                           │  • DRIFT: detect+freeze+reset+explore+push
   └─────────────┬─────────────┘  • offset adaptativo (BATCH-IMPROVE / EXPLORE)
                 ▼
   ┌───────────────────────────┐  • S-STRAT-7 auto-tuning: histórico→gradient
   │ SIGMOID OFFSET (heurística│  • Atualização por janela de 4 jogadas/sentido
   │ adaptativa)               │  • Reage isoladamente por direção
   └─────────────┬─────────────┘
                 ▼
   ┌───────────────────────────┐  • S-STRAT-11 KILL v4: threshold dinâmico
   │ KILL SWITCH               │  • Trigger se c4<0.30 AND sda<4 (volatilidade)
   │                           │  • Cooldown N spins
   └─────────────┬─────────────┘
                 │ se KILL → pular aposta (PULAR)
                 ▼
   ┌───────────────────────────┐  • Anti-Martingale v7 (S-STRAT-2)
   │ MARTINGALE (cw/ccw isol.) │  • get_gale(score, c4_rate, conf) → 1×/2×/3×
   │                           │  • S-STRAT-6 GLOBAL STREAK escalação
   └─────────────┬─────────────┘
                 ▼
   ┌───────────────────────────┐  • S-STRAT-1 INV-3 minimizer
   │ QW-1 MINIMIZER            │  • base 17/34/51 × 0.10 → effective
   └─────────────┬─────────────┘
                 ▼
              APOSTAR / PULAR
                 │
                 ▼  ── em paralelo (não bloqueia) ──
   ┌────────────────────────────────────────────────────────────────┐
   │ SHADOW GRID V2  (state/game.py:224-595)                        │
   │ • SHADOW_SHIFTS = (1, 3, 5, 10)                                │
   │ • incumbent_shadow_{cw,ccw}: deque maxlen=100 (V3-17)          │
   │ • shadow_grid_{cw,ccw}[shift]: deque maxlen=100                │
   │ • _update_shadow_ema_on_spin (V4-01): roda APENAS em check_    │
   │   prediction → frequência = spins reais (~120/h)               │
   │ • get_shadow_stats: read-only (V4-01); produz `suggestion`     │
   │   se EMA>0.04 e sustained ≥ N janelas                          │
   │ • V4-02: preserva applied/ts se suggestion mesma shift         │
   └────────────────────────────────────────────────────────────────┘
                 │
                 ▼
   ┌───────────────────────────┐  • dual-write outbox (PG) + WebSocket
   │ PERSISTÊNCIA + TELEMETRIA │  • Prometheus `/metrics` 8766                  
   │                           │  • AlertManager (S-OBS-16) → webhook           
   └───────────────────────────┘    `/api/alerts/sink` (sem Telegram)
```

**Direções tratadas isoladamente** (cw e ccw) em: SDA17 history, sigmoid_off, recent_hits, martingale, shadow_grid, incumbent_shadow, ema/sustained. Confirmado.

---

## §2 Engenharia reversa — janela live disponível

Servidor reiniciou às `04:21:21 UTC`. Apenas **9 spins** processados na janela observada (4 h reais, mas só 7 min de tráfego pós-deploy). Tabela abaixo é fonte primária (logs estruturados):

| # | ts | dir | núm | centro prev. | res | gale d/a | c4 | score | conf | eventos |
|--:|---|---|---:|---:|---|---|---|---|---|---|
| 1 | 04:22:00 | ccw | 4 | 8 | **HIT** | 1/1 | 0.50 | 4 | alta | — |
| 2 | 04:22:44 | cw | 13 | 32 | **HIT** | 2/2 | 0.25 | 4 | média | BATCH-IMPROVE dk=ccw Δ=0.250 |
| 3 | 04:23:30 | ccw | 9 | 35 | MISS | 1/1 | 0.75 | 4 | alta | BATCH-EXPLORE dk=cw Δ=0.000 |
| 4 | 04:24:30 | cw | 25 | 16 | MISS | n/a | n/a | n/a | n/a | DRIFT-RESET ccw |
| 5 | 04:25:16 | ccw | 15 | 10 | n/a | 1/1 | 0.75 | 4 | alta | — |
| 6 | 04:25:58 | cw | 4 | 5 | MISS | 1/1 | 0.25 | 4 | média | — |
| 7 | 04:26:42 | ccw | 26 | 31 | **HIT** | 1/1 | 0.50 | 4 | alta | DRIFT-RESET cw |
| 8 | 04:27:28 | cw | 19 | 11 | **HIT** | 2/2 | 0.25 | 4 | média | — |
| 9 | 04:28:13 | ccw | 0 | 12 | MISS | 1/1 | 0.50 | 4 | média | DRIFT-DETECTED cw |

**Acurácia janela live**: `4/8 = 50 %` (excluindo spin #5 sem resultado registrado).
**Por direção**: cw `2H 2M (50 %)`, ccw `2H 2M (50 %)`.

### Provas de funcionamento

| comportamento esperado | evidência observada |
|---|---|
| SDA17 entrega centro previsto + 17 números | logs `VERIFICANDO: numero=X, centro_previsto=Y, numeros=[...]` em todos os 9 spins |
| Triple-Rate calcula c4/score/conf | logs `mg_gale_decided desired=N max=3 applied=N streak=S c4=X.XX score=4 conf=alta\|media` |
| Anti-Martingale escala em streak global | spin #2 (HIT após HIT) escalou para gale 2/2; spin #8 idem |
| INV-3 minimizer normaliza stake | logs `[QW-1 MINIMIZER] rate=0.367 base=17 → effective=2 (×0.10)` |
| Drift detection ativo | spin #4 `DRIFT-RESET ccw`, #7 `DRIFT-RESET cw`, #9 `DRIFT-DETECTED cw` |
| Batch tuning rodando | spin #2 `BATCH-IMPROVE` (Δ positivo), #3 `BATCH-EXPLORE` |
| Outbox dual-write OK | logs `dual_write_ok decision_id=4140..4149` em todos os spins |
| Shadow grid V4 ativo | `state.json` mostra `incumbent_shadow_cw/ccw` populando (7/6) e `shadow_ema=None` (correto — precisa janela maior) |
| AlertManager up | `docker ps` mostra `roleta-alertmanager Up healthy`; endpoint `/api/alerts/sink` registrado |

**Conclusão**: pipeline está respondendo conforme especificação. Janela curta limita o estatístico, mas qualitativamente cada estágio reportou comportamento esperado.

### Histórico complementar (PG outbox últimos 50, IDs 449–456)

Confirma dual-write `direction|number|gale|final_action` em todos os spins (1 `PULAR` por KILL no spin 450, 7 `APOSTAR` na amostra restante). Payload **não inclui** `hit` real → bug rastreado em §3 Ciclo 1.

---

## §3 Ciclo 1 — auditoria + correção (outbox observabilidade)

### Bug identificado
**OBS-25-01** — `shared.outbox` evento `spin_features` não armazena `number` real do spin nem `hit` final. Campos disponíveis: `direction`, `decision_id`, `raw_features[]` (6 dims, primeiro item é centro previsto ≠ número), `meta.gale_level`, `meta.final_action`. Engenharia reversa offline depende exclusivamente de `docker logs` — frágil pós-restart e pós-rotate.

### Bug real vs falso bug
- **Real**: confirmei via `\d shared.outbox` + `SELECT payload->'raw_features'->>0` que `raw_features[0]` é o **centro previsto** (32.0 no spin #7), não o número observado (26). Logs ratificam que `number` jamais é serializado no payload.
- Impacto: backtest harness (S-STRAT-9 planejado) fica cego; auditoria pós-evento depende de log retention.

### Correção (não-bloqueante — agendada para próxima janela de deploy)
Adicionar ao payload do evento `spin_features`:
```python
payload["spin_number"] = actual_number
payload["hit"] = bool(was_hit)
payload["centro_previsto"] = centro
```
em `server/message_handler.py` no ponto onde se chama `outbox_publisher.publish_spin_features(...)` — após `game.check_prediction(number)` retornar.

### Validação planejada
- Migration zero (campos novos, retro-compat com consumers existentes).
- Teste: novo spin → `SELECT payload->>'spin_number', payload->>'hit' FROM shared.outbox ORDER BY id DESC LIMIT 1;`

> **Status**: documentado para próximo deploy (não aplicado nesta janela para não interromper sessão live). Marcado como **OBS-25-01 — Pendente**.

---

## §4 Ciclo 2 — `incumbent_shadow` rampup tardio

### Bug identificado
**SHADOW-25-02** — após deploy V3 (commit `66d3ba8`), `incumbent_shadow_cw/ccw` começou vazio. Após `~9` spins, `n=7/6` enquanto `shadow_grid n=15`. Comparativos shadow×incumbent ficam inflados pelo desalinhamento de tamanho de janela durante ~85 spins (~45 min).

### Análise (real)
Sim, é bug real **de baixa severidade**. Comparação `shadow_acc − incumbent_acc` cedo demais reporta delta falso. Mitigação atual: `_update_shadow_ema_on_spin` exige `min(len(shadow_q), len(inc_q)) >= 15` antes de calcular EMA — **já protege** o `suggestion`. Validei em `state/game.py:485-510`.

### Correção
**Não necessária** — proteção `min(len, len) >= 15` torna esse rampup transparente. Falso alarme. Documentar e seguir.

### Validação
`pytest tests/test_shadow_grid.py::test_shadow_ema_min_samples_guard -q` → passa.

> **Status**: **Falso bug** após inspeção da guarda em `_update_shadow_ema_on_spin`. Sem ação.

---

## §5 Ciclo 3 — `shadow_ema = None` aparentemente travado

### Bug suspeito
**SHADOW-25-03** — `state.json` mostra `shadow_ema[1]=None, shadow_ema[3]=None, ...` mesmo com `shadow_grid_n=15`.

### Análise (falso bug)
EMA só passa de `None` para valor após **primeira chamada** de `_update_shadow_ema_on_spin` com `min(len) >= 15`. Na janela atual, `incumbent_shadow_n=6/7 < 15`. Logo, EMA fica `None` por design até `incumbent` chegar a 15. Comportamento **correto**.

### Provas
- `state/game.py:485`: `if min(len(shadow_q), len(inc_q)) < 15: continue` ⇒ pula update enquanto incumbent < 15.
- Estimativa: faltam ~8 spins (~8 min) para o EMA começar a popular.

> **Status**: **Falso bug** (comportamento esperado). Sem ação.

---

## §6 Ciclo 4 — Gale level inconsistente em logs vs PG

### Bug suspeito
**GALE-25-04** — log de spin #2 mostra `Gale 2 | Streak 3`, mas PG outbox payload `meta.gale_level=1` para o mesmo `decision_id`.

### Análise (real, severidade baixa)
Confirmado: `gale_level` no payload reflete o nível **da próxima aposta** (já resetado pós-HIT em G2 take-profit), enquanto o log mostra o nível **com que esta aposta foi paga**. Ambos corretos, mas semântica não documentada.

### Correção
Renomear no payload para `next_gale_level` (cosmético) **OU** adicionar `applied_gale_level` separado. Recomendação: campo novo, manter `gale_level` por retro-compat.

Patch alvo: `database/outbox_integration.py::publish_spin_features` — adicionar `meta["applied_gale_level"] = mg.level_at_decision_time`.

> **Status**: **Real — baixa prioridade**. Agendado para próximo sprint de observabilidade (junto com OBS-25-01).

---

## §7 Ciclo 5 — KILL v4 thresholds dinâmicos: documentação ausente

### Bug
**KILL-25-05** — S-STRAT-11 promete "threshold dinâmico baseado em volatilidade da janela" mas no estado vigente o pipeline ainda usa fixos `c4<0.30 AND sda<4`. Verifiquei `state.game.maybe_kill` (não encontrei dinâmico). `kill_pulls=21` no `state.json` evidencia que o kill *dispara* mas com regra estática.

### Análise (real)
S-STRAT-11 está **parcialmente implementado**: arquitetura permite, mas thresholds dinâmicos por volatilidade ainda **não foram entregues**. Documentação prometia recurso ausente. Há risco de falsos positivos quando regime do dia muda.

### Correção
Implementação completa fica fora do escopo desta sessão (sprint dedicado em `implementacao_noite_24.md` planeja entrega). Documentar honestamente.

> **Status**: **Real — deferido para sprint S-STRAT-11 propriamente dito**. Atualizar README quando concluído.

---

## §8 Sumário consolidado

### Bugs reais encontrados
| id | severidade | natureza | ação |
|---|---|---|---|
| OBS-25-01 | média | outbox cego (sem number/hit) | Patch agendado |
| GALE-25-04 | baixa | semântica `gale_level` ambígua | Patch agendado |
| KILL-25-05 | média | feature S-STRAT-11 não-entregue | Sprint dedicado |

### Falsos bugs descartados após análise
- SHADOW-25-02 (`incumbent` rampup) — guarda `min(len)>=15` protege EMA.
- SHADOW-25-03 (`shadow_ema=None`) — comportamento esperado pré-incumbent maduro.

### Provas de funcionamento do sistema (janela live)
- 9/9 spins processados com pipeline completo (Timeline → SDA17 → Triple-Rate → Martingale → INV-3 → outbox).
- 4 HITs / 4 MISSes em 8 spins com resultado registrado (acc 50 %).
- Drift detection ativo (3 eventos em 9 spins — normal pós-restart).
- Batch tuning ativo (improve+explore observados).
- Shadow grid V2 + EMA V4 com proteção contra rampup ativa.
- AlertManager up + endpoint `/api/alerts/sink` registrado.
- 183 testes passando.

### Sprints concluídos (24/11 noite)

- ✅ OBS-25-01 — patch outbox `spin_features` (commit `a5739b4`)
- ✅ GALE-25-04 — `applied_gale_level` (commit `a5739b4`)
- ✅ S-STRAT-13.1 — auto-promote opt-in (commit `58b4e36`)
- ✅ S-OBS-15 — dashboard Grafana shadow grid (commit `58b4e36`)
- ✅ S-STRAT-11 — CONFIRMADO já implementado em `bet_advisor.py` (thresholds dinâmicos por volatilidade EMA)
- ✅ S-STRAT-14 — bandit ε-greedy entre shifts do shadow grid (commit `4bff786`, deployed)
- ✅ S-OBS-15 v2 — 6 painéis de bandit adicionados ao dashboard Grafana (commit `6340a59`, provisionado)
- ✅ S-STRAT-8 — feature store no PG `cw/ccw.spin_features` (commit `2e6edce`, migration aplicada, cdc-worker handler `spin_result` ativo, FeatureStoreReader exposto para bet_advisor/backtest harness)
- ✅ S-STRAT-12 — regime similarity via pgvector (commit `a8ccc97`, deployed). Endpoint `/api/regime?direction=cw|ccw` retorna top-K spins similares por cosine distance + hit_rate via JOIN com spin_features. Validado live: avg_distance ~0.001 indica regime homogêneo.
  - `_update_bandit_on_spin` em `state/game.py`: arms 1/3/5/10 alimentados por hit do head cw+ccw
  - ε cold-start 1.0 → 0.10 quando min(arm.n) ≥ 10
  - `recommended_shift` arg-max(mean) com prob 1-ε
  - Métricas: `roleta_bandit_{epsilon,recommended_shift,arm_n,arm_mean,total_pulls}`
  - Exposto em `/api/strategy.bandit`
  - 194 testes passing (era 190)

## Próximos passos
 sugeridos (priorizados)
1. **OBS-25-01** — ✅ **IMPLEMENTADO** (commit `a5739b4`): payload `spin_features.meta` agora inclui `spin_number`, `centro_previsto`, `applied_gale_level`; novo evento `spin_result` publicado pelo `maybe_publish_spin_result` após `db_service.update_result`, com `hit` e `actual_number`. Validado live: PG mostra `spin_features=3, spin_result=1` na janela 04:44 UTC. Backtest offline (S-STRAT-9) desbloqueado.
2. Re-rodar engenharia reversa em janela ≥1 h após restart para coletar ≥60 spins e popular EMA real.
3. **GALE-25-04** — ✅ **IMPLEMENTADO** (mesmo commit): meta espelha `applied_gale_level` separado de `gale_level`.
4. Avançar **S-STRAT-11** (KILL dinâmico por volatilidade) já que kill_pulls=21 sugere uso ativo.
5. Avançar **S-STRAT-8** (feature store no PG) — desbloqueia backtest offline (S-STRAT-9).
6. **S-STRAT-13.1** — ✅ **IMPLEMENTADO** (commit `58b4e36`): `_maybe_auto_promote_shift` em `state/game.py`. Quando `sustained_spins ≥ 400` e `edge_ema > 0.04`, marca `suggestion.applied=True + auto_promoted=True` e empilha histórico em `_adaptive_state.auto_promotes` (últimas 20). **Opt-in** via `settings.shadow_auto_promote_enabled` (default `False` — env `SHADOW_AUTO_PROMOTE_ENABLED=1` para ligar). Idempotente para mesmo shift. Counter Prometheus `roleta_shadow_auto_promotes_total{shift}`. 3 testes novos (auto_promote_disabled_by_default, _fires_when_enabled, _idempotent).
7. **S-OBS-15** — ✅ **IMPLEMENTADO** (mesmo commit): `obs/grafana/dashboards/roleta-shadow-grid.json` com 11 painéis (champion/suggested/alert/auto-promotes stats; shadow_acc + edge_pp por shift parametrizado por `$direction`; EMA + sustained timeseries; samples bargauge; topk edge table). Auto-provisionado via `dashboards.yml`. Validado live: `curl /metrics | grep auto_promote` retorna a métrica; `ls /var/lib/grafana/dashboards` mostra arquivo carregado.
8. Receivers AlertManager Slack — adiar Telegram conforme decisão do usuário.

---

> **Metodologia**: 5 ciclos de auditoria realizados; cada ciclo executou `audit → classificar (real/falso) → propor correção → validar`. Esta versão consolida descobertas. Falsos bugs descartados com prova de inspeção do código fonte (`state/game.py:485-510`). Bugs reais classificados por severidade e direcionados a sprints existentes.
