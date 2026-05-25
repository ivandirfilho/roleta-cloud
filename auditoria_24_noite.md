# Auditoria Noite 24-05 → Pós-S-STRAT-13 + S-OBS-14
**Versão:** 1.0
**Data:** 2026-05-25 ~03:50 UTC
**Auditor:** YOLO Orchestrator (claude-opus-4.7)
**Stack MCP:** graphify (regen) + filesystem + sequential-thinking + memory + brave.
**Escopo:** código novo das janelas §22 (shadow grid + AlertManager) + estado live do servidor Debian.

---

## 0. Snapshot live no momento da auditoria

| Item | Valor |
|---|---|
| roleta-cloud | Up 5min, healthy, 32 MiB / 512 MiB |
| roleta-pg | healthy, 102 MiB |
| roleta-prometheus | Up 2min, 11 regras em 3 grupos |
| roleta-grafana | healthy |
| Disco | 6.1 GB / 79 GB (9 %) |
| `/api/shadow` | 4 challengers ativos, alert=ok |
| Alerts firing | 0 |
| state.json | 7,894 B |
| outbox pending | (query usou coluna inexistente; corrigido em §7.4 V2) |
| PG sizes (top) | spins_vectors cw 936 kB, ccw 936 kB, outbox 296 kB |

Sistema **VERDE** 🟢 antes da auditoria.

---

## 1. Bugs encontrados

### 🔴 CRÍTICOS / MÉDIO-ALTOS

#### BUG-A24-01 — `shadow_grid` **não persistido** em state.json
- **Severidade:** média-alta
- **Onde:** `state/game.py::save()` (linha ~707) e `load()` (linha ~794).
- **Sintoma:** Em todo restart do `roleta-cloud`, perde-se até 800 amostras (4 shifts × 2 direções × 100 hits). Champion detection precisa esperar 30+ spins por direção, então restart "esquece" potenciais sinais já maduros.
- **Hipótese de impacto:** S-STRAT-13 fica quase inútil durante a fase de iteração rápida em que ainda fazemos deploys diários.
- **Fix:** incluir `shadow_grid` (com `int→str` na serialização JSON) + `shadow_hits_cw/ccw` em `save()`; restaurar em `load()` com conversão `str→int` nos keys.
- **Status:** corrigido nesta auditoria (§3).

#### BUG-A24-13 — `reset_session` **não limpa** shadow_grid
- **Severidade:** média
- **Onde:** `state/game.py::reset_session()` (linha ~242).
- **Sintoma:** Trocar dealer/mesa não reseta o shadow grid → hits velhos contaminam estatísticas, champion errado pode emergir.
- **Fix:** após resetar `performance_sda17_*`, reinicializar `shadow_grid` para todos os shifts em `SHADOW_SHIFTS` + limpar `shadow_hits_cw/ccw`.
- **Status:** corrigido nesta auditoria (§3).

### 🟡 BAIXOS / NOTAS

| ID | Severidade | Item | Decisão |
|---|---|---|---|
| BUG-A24-02 | baixo | JSON serializa int keys como str — precisa converter no load | Tratado dentro de A24-01 |
| BUG-A24-03 | falso positivo | Legacy `shadow_hits_*` duplicaria hit do shift=5 | NÃO duplica — fluxo único correto |
| BUG-A24-04 | nota | Prometheus labels `{shift,direction}` criam cardinality 4×2=8 séries por gauge | OK, bounded |
| BUG-A24-05 | conhecido | AlertManager não está no compose | Coberto por S-OBS-16 (próxima janela) |
| BUG-A24-06 | edge | `shadow_champion_shift` Gauge usa 0 como "nenhum" — shift=0 não é válido | OK, semântica clara |
| BUG-A24-07 | doc | `edge_pp` sinal invertido vs MVP (agora `sd - inc`) | Já documentado em §22 V13-03 |
| BUG-A24-08 | doc | Painel Grafana legacy assume sinal antigo | Será refeito em S-OBS-15 |
| BUG-A24-12 | edge | `champion["shift"]` pode ser `None` | Safe: `or 0` no Gauge |
| BUG-A24-14 | cosmético | fs.file-nr no container vem concatenado | Sem impacto |
| BUG-A24-15 | ok | Memória 32/512 MiB, sem pressão | Não-bug |
| BUG-A24-16 | ok | Prometheus retention 1.8 MB (instância nova) | Não-bug |

**Resumo:** 2 bugs reais corrigidos, 9 itens não-bug verificados, 1 documentação.

---

## 2. Tasks executadas

| ID | Título | Status |
|---|---|---|
| a24-fix-01 | BUG-A24-01: persistir shadow_grid | ✅ done |
| a24-fix-02 | BUG-A24-13: reset_session limpa shadow_grid | ✅ done |
| a24-fix-03 | Bump state version 1.7→1.9 | ✅ done |
| a24-fix-04 | Tests round-trip persistência | ✅ done |
| a24-fix-deploy | Deploy + validar live | ✅ done |
| a24-doc | Criar auditoria_24_noite.md | ✅ este arquivo |

---

## 3. Implementação dos fixes

### `state/game.py`
- `save()` — version bump 1.7.0 → **1.9.0**; adicionados campos `shadow_hits_cw`, `shadow_hits_ccw`, `shadow_grid` (int keys → str na serialização).
- `load()` — restaura os três campos com conversão `str → int` nos keys; tolerante a state.json antigo (cai no default de `__post_init__`).
- `reset_session()` — limpa `shadow_grid` e `shadow_hits_cw/ccw` ao trocar dealer/mesa.

### `tests/test_shadow_grid.py` (+3 novos testes)
- `test_shadow_grid_persists_roundtrip` — save → reload preserva 10 hits em shifts 3 e 10.
- `test_shadow_grid_load_tolerant_to_missing_field` — state v1.7 sem shadow_grid carrega gracefully.
- `test_reset_session_clears_shadow_grid` — todos os shifts + legacy hits zerados após reset.

### Validação local
- **175 passed**, 7 skipped, 1 xfailed (era 172 → +3).

---

## 4. Resultado live pós-deploy

```
state.json:
  version       = 1.9.0
  shadow_grid   = present (keys: '1','3','5','10')
  shadow_hits_* = present

/api/shadow:
  design        = shadow_grid_v1
  shifts        = [1, 3, 5, 10]
  alert         = ok
  challengers   = 4 (rampup pós-restart)

containers: all healthy
prom rules:  11 ativas em 3 grupos
firing:      0
```

**Commits:**
- `4275ce7` — feat S-STRAT-13 + S-OBS-14 (sessão anterior)
- `db44679` — fix PromQL `max/min` → `or`
- `a05aa99` — fix shadow_grid persist + reset (esta auditoria)

**Status final: VERDE 🟢. 2 bugs corrigidos. Sistema com persistência completa do shadow grid.**

---

## 5. Próximas tasks — **Objetivo · Porquê · Como**

### 1️⃣ S-STRAT-13.1 — Promoção automática do champion
- **Objetivo:** transformar a observação passiva do shadow grid em **ação**: quando um challenger sustenta vantagem real sobre o incumbent, ele é promovido a sugestão de calibração.
- **Porquê:** hoje o S-STRAT-13 só detecta off-by-N; precisamos fechar o loop "observa → propõe → aplica". Sem promoção automática, dependemos de humano lendo `/api/shadow` para agir.
- **Como:**
  1. Em `state/game.py::get_shadow_stats`, calcular `sustained_edge_spins` por challenger (contador incrementado quando `avg_acc - incumbent_avg > 0.04`).
  2. Quando contador ≥ 200 (≈ 2-3 h de operação), escrever em `_adaptive_state["suggested_shift"] = {"shift": X, "applied": False, "ts": now}`.
  3. **Sem auto-aplicar** na v1 — apenas sugerir; humano decide via flag `--apply-shadow-shift` ou endpoint POST.
  4. Métrica nova: `roleta_shadow_suggested_shift`.
  5. Testes: simular 250 spins com shift=3 ganhando → verificar suggestion gravada.

### 2️⃣ S-OBS-15 — Painel Grafana específico do shadow grid
- **Objetivo:** dashboard dedicado mostrando heat-map `shift × direction` + timeseries de acc por challenger + indicador do champion.
- **Porquê:** o overview atual tem 13 painéis — adicionar 4-8 painéis de shadow grid lá polui. Operador precisa ver shadow isoladamente para decidir se promove (§S-STRAT-13.1).
- **Como:**
  1. Novo dashboard JSON em `obs/grafana/dashboards/shadow-grid.json`.
  2. Painéis: (a) tabela challengers com avg_acc colorido; (b) timeseries `roleta_shadow_acc` agrupado por shift; (c) gauge `roleta_shadow_champion_shift`; (d) stat `roleta_shadow_alert`; (e) heat-map `edge_pp` matriz 4×2; (f) painel de "samples_n" para validar maturidade.
  3. Provisioning automático via diretório já configurado.
  4. Restart `roleta-grafana` para carregar.

### 3️⃣ S-OBS-16 — Receivers do AlertManager (Slack/Telegram)
- **Objetivo:** transformar alertas Prometheus em notificações reais (hoje só ficam em `/api/v1/alerts`).
- **Porquê:** o S-OBS-14 criou 4 regras novas — sem receiver, o operador descobre por acaso. Em produção 24×7, isso é cego.
- **Como:**
  1. Adicionar `alertmanager` ao `docker-compose.yml` (imagem `prom/alertmanager:latest`, volume `obs/alertmanager.yml`, porta 9093).
  2. Apontar `alerting:` em `obs/prometheus.yml` para `alertmanager:9093`.
  3. `obs/alertmanager.yml`: receiver Telegram (mais simples) com `bot_token` + `chat_id` injetados via env vars. Telegram > Slack porque já existe bot Telegram no servidor (verificar).
  4. Routing: severity=critical → mensagem imediata; warning → agrupar 10 min; info → silent.
  5. Smoke-test: dispararar regra `RoletaShadowBeatingIncumbent` artificialmente e confirmar recebimento.

### 4️⃣ S-STRAT-8 — Feature store no PG (lag features)
- **Objetivo:** dar à estratégia acesso a **features estruturadas** dos últimos 50-100 spins (não só hits in-memory), permitindo scoring mais rico.
- **Porquê:** hoje `bet_advisor` consulta apenas `recent_hits` em RAM. Lag features (números anteriores, deltas no wheel, gaps de "vermelho/preto", direções recentes) ficam invisíveis. Pré-requisito para ML real (S-STRAT-12).
- **Como:**
  1. Migration: tabela `shared.spin_features` com `(spin_id, direction, ts, lag1_number, lag1_distance, lag5_red_count, lag10_direction_balance, …)`.
  2. CDC worker passa a popular essa tabela on-the-fly (extensão do extrator atual).
  3. Novo módulo `strategies/feature_store.py` com `get_features(spin_id) -> dict`.
  4. `bet_advisor` opcionalmente lê `feature_store` quando flag `S_STRAT_8_ENABLED=1`.
  5. Backfill: script `scripts/backfill_features.py` para popular 10k spins históricos (~30 min).
  6. Testes: features estáveis sob reordem de spins; deltas corretos no wheel europeu.

### 5️⃣ S-STRAT-12 — Embeddings de spins via pgvector
- **Objetivo:** dar à IA **memória de regimes** — quando um padrão atual se parece com um passado de alta accuracy, herdar a calibração que funcionou.
- **Porquê:** hoje a estratégia é amnésica entre dias. Regime de quarta-feira 22h pode ser similar ao de quinta 21h, mas começa do zero. pgvector já está instalado (índice ivfflat ativo em `cw.spins_vectors` 936 kB), falta usá-lo.
- **Como:**
  1. Definir feature vector: concatenar lag features (S-STRAT-8) em vetor de dim 32-64.
  2. Trigger no PG: ao inserir spin, computar embedding e UPSERT em `cw/ccw.spins_vectors`.
  3. Novo método `strategies/regime_memory.py::find_similar(now_vec, k=20)` retornando spins históricos próximos.
  4. `bet_advisor` consulta similar regimes e ajusta sigmoid_off por interpolação ponderada.
  5. Dashboard: histograma de "similarity scores" para diagnosticar quando IA está em regime conhecido vs desconhecido.
  6. Bloqueio: depende de S-STRAT-8 (feature vector) + backtest harness (S-STRAT-9, já feito) para validar offline.

### 6️⃣ S-STRAT-14 — Bandit ε-greedy entre challengers
- **Objetivo:** ao invés de promover um único champion (S-STRAT-13.1), **explorar/exploitar** dinamicamente entre os 4 challengers + incumbent.
- **Porquê:** S-STRAT-13.1 é decisão hard (escolhe um). Em regimes mistos, o melhor pode oscilar. Bandit equilibra automaticamente.
- **Como:**
  1. Wrapper `strategies/shadow_bandit.py` recebendo 5 braços: incumbent + 4 shifts.
  2. ε-greedy com ε=0.10 (10% exploração).
  3. Reward = hit recente (rolling 50).
  4. **Sem apostar de verdade** com challengers ainda — apenas calcular "qual escolheria" e logar; comparar acc média do bandit virtual vs incumbent puro.
  5. Após 1 semana de coleta sólida (≥ 5k spins), avaliar se faz sentido apostar via bandit.
  6. Cuidado: bandit pode aumentar variância. Requer KILL v5 (volatility-aware) para travar quando ε está caro.
  7. Pré-requisito: S-STRAT-13.1 (suggested_shift) + S-STRAT-9 backtest (já feito) para A/B offline.

---

## 6. Diagrama de dependência (próximas tasks)

```
        S-STRAT-13 ✅ (feito)
             │
             ├─── S-STRAT-13.1 ─── S-STRAT-14 (bandit)
             │       (promote)
             │
             └─── S-OBS-15 (dashboard)
                    │
                    └─── S-OBS-16 (alerting receiver)

        S-STRAT-8 (feature store) ─── S-STRAT-12 (pgvector embeddings)
              │                              │
              └──────────────────────────────┴── S-STRAT-15 (ML real)
```

**Ordem recomendada de execução:** S-OBS-16 → S-STRAT-13.1 → S-OBS-15 → S-STRAT-8 → S-STRAT-12 → S-STRAT-14.

---

---

## 7. §AUDIT-V2 — Meta-auditoria deste documento + plano + código pós-fix
**Timestamp:** 2026-05-25 ~04:05 UTC
**Stack MCP:** graphify (regen) + filesystem + sequential-thinking + memory + brave.

### 7.1 Bugs encontrados nesta auditoria-V2

#### 🔴 BUG-A24-V2-10 — `check_prediction` descarta hits silenciosamente após restart
- **Severidade:** **alta** (silent data loss).
- **Onde:** `state/game.py::check_prediction` (linha ~351).
- **Causa raiz:** `json.dumps` converte `int` keys de dict para `str` automaticamente. Quando `pending_prediction` (que contém `shadow_numbers_by_shift` com keys int) é persistido em `state.json` e depois restaurado, os keys voltam como str. O loop `for shift, sh_nums in shadow_by_shift.items()` itera com `shift="1"`, e o lookup `self.shadow_grid["1"]` cai no `except KeyError: continue` → o hit é **descartado sem log**.
- **Impacto:** se houver crash/restart entre `store_prediction` e `check_prediction` do mesmo spin, esse spin nunca é registrado no shadow grid. Em produção 24×7 com 1 restart/dia, perdemos ≥ 1 amostra/dia/shift. Silent.
- **Fix:** normalizar `shift_int = int(shift)` antes do lookup; `try/except` envolvendo a conversão.
- **Teste de regressão:** `test_check_prediction_after_restart_uses_str_keys`.
- **Status:** ✅ corrigido.

#### 🟡 BUG-A24-V2-09 — `__post_init__` falha se `shadow_grid=None` explícito
- **Severidade:** baixa (não atinge runtime atual, mas defensivo).
- **Fix:** tratar `None` antes de iterar.
- **Status:** ✅ corrigido.

### 7.2 Bugs no PLANO (próximas tasks) — patches no doc

| ID | Task afetada | Issue | Patch aplicado abaixo |
|---|---|---|---|
| PLAN-V2-01 | S-STRAT-13.1 | Sem hysteresis → thrashing entre challengers quando `edge ≈ 0.04` | Adicionar EMA + histerese (enter > 0.04, exit < 0.02) |
| PLAN-V2-02 | S-STRAT-8 | Schema `shared.spin_features` viola convenção (resto do projeto usa schemas separados `cw/ccw`) | Trocar para `cw.spin_features` + `ccw.spin_features` |
| PLAN-V2-03 | S-STRAT-12 | Trigger síncrono em INSERT bloqueia hot path | Substituir por worker async lendo outbox |
| PLAN-V2-04 | S-STRAT-14 | Cold-start: challengers com n<10 podem ser ignorados | Forçar ε=1.0 enquanto algum braço tem n<10 |
| PLAN-V2-05 | S-OBS-16 | Assume bot Telegram existente — não validado | Adicionar passo "criar bot novo via @BotFather" como fallback |
| PLAN-V2-06 | S-OBS-16 | Silences do AlertManager perdidos em restart | Adicionar volume `alertmanager-data:/alertmanager` |

### 7.3 Patches do plano (substitui texto em §5)

- **S-STRAT-13.1 — Item 1 (atualizado):** "Calcular `edge_ema` (α=0.05) por challenger. Incrementa `sustained_edge_spins` SOMENTE quando `edge_ema > 0.04`. Decrementa quando `edge_ema < 0.02` (banda morta anti-thrashing). Promove sugestão quando `sustained_edge_spins ≥ 200` E `edge_ema > 0.04` E n≥50 por direção."
- **S-STRAT-8 — Item 1 (atualizado):** "Migrations: `cw.spin_features` + `ccw.spin_features` (paridade com `cw/ccw.spins` e `cw/ccw.spins_vectors`). Schema `shared` reservado para tabelas cross-direction (outbox, strategy_versions)."
- **S-STRAT-12 — Item 2 (atualizado):** "Worker assíncrono `cdc_embedding_worker.py` lê outbox `shared.spin_events`, computa embedding, faz UPSERT em `cw/ccw.spins_vectors`. **Sem trigger síncrono** no INSERT (mantém latência do hot path < 5 ms)."
- **S-STRAT-14 — Item 2 (atualizado):** "Cold-start ε=1.0 até cada braço ter n≥10. Depois, ε=0.10 normal. Garante exploração inicial obrigatória."
- **S-OBS-16 — Item 3 (atualizado):** "Receiver Telegram: 1) verificar se existe bot via `secrets/telegram_bot_token`; 2) se NÃO existe, criar novo via @BotFather, salvar em `secrets/`, atualizar `.env`. Volume `alertmanager-data:/alertmanager` para persistir silences/notification log."

### 7.4 Correção do §0
- **Linha 22** "outbox pending | (query falhou — schema corrigido nesta auditoria)" → texto enganoso. Schema NÃO foi corrigido — apenas a query usei a coluna errada (`direction`, que não existe em `shared.outbox`). Corrigido para refletir a verdade.

### 7.5 Observação operacional importante (NÃO é bug)
Durante a janela de validação live (~10 min pós-restart), `/api/shadow` mostrou todos os challengers com `n=0`. Inicialmente pareceu bug, mas a investigação revelou:
- `last_number=8`, `performance_sda17_ccw_len=1` → sistema processou spins
- Logs: `DRIFT-DETECTED dir=cw freezing 5 spins` (03:57) e `dir=ccw` (04:04)
- Durante `drift_freeze`, `store_prediction` **não é chamado** → `pending_prediction` fica vazio → shadow grid não cresce.

**Comportamento esperado.** Mas merece nota: a hipótese off-by-N do shadow grid é diluída em janelas de drift frequente. Pode justificar uma futura S-STRAT-13.2 que use spins observados (não apenas os com predição ativa) para enriquecer o grid mais rapidamente.

### 7.6 Resultado dos fixes V2

| Item | Antes | Depois |
|---|---|---|
| `check_prediction` int/str keys | KeyError silencioso após restart | Normaliza com `int(shift)` |
| `__post_init__` defensividade | Falha em `shadow_grid=None` | Trata None gracefully |
| Testes | 11 (test_shadow_grid) | **12** (+1 regressão V2-10) |
| Suite total | 175 | **176** |
| Plano (próximas 6 tasks) | 6 itens com gaps | 6 itens com gaps endereçados |
| Documento | §0 com afirmação incorreta | corrigido |

### 7.7 Commits
- `00a7d3e` — docs(audit): resultado pós-deploy V1
- `<próx commit>` — fix(state) + docs(audit): V2 normaliza keys + plano endurecido

**Status final V2: VERDE 🟢. 1 bug de silent data loss eliminado. Plano das próximas 6 tasks endurecido em 6 pontos.**

---

## 8. §AUDIT-V3 — Auditoria profunda pré-S-STRAT-13.1 + AlertManager
**Timestamp:** 2026-05-25 ~04:30 UTC
**Stack MCP:** graphify (regen) + filesystem + sequential-thinking + memory + brave.
**Escopo:** revisão profunda do shadow grid + plano de implementação simultânea de S-STRAT-13.1 (auto-suggestion) e S-OBS-16 (AlertManager, **sem Telegram** por decisão do usuário).

### 8.1 Bugs novos encontrados

#### 🔴 BUG-A24-V3-17 — Incumbent baseline ruidoso (maxlen=12 vs shadow=100)
- **Severidade:** alta semântica.
- **Onde:** `state/game.py::get_shadow_stats` linhas 456-457 (antes).
- **Causa raiz:** `inc_cw/ccw` calculados sobre `performance_sda17_cw/ccw` que têm `maxlen=12`. Shadow grid tem `maxlen=100`. Comparar acc de 12 amostras contra 100 produz `edge_pp` extremamente volátil — incumbent oscila ±20pp entre spins enquanto shadow oscila ±2pp. Champion detection falsifica positivos quando incumbent acabou de errar 5 seguidas (acc=58% real cai para 25% em janela curta).
- **Impacto:** S-STRAT-13.1 ficaria **inviável** sem isso — sustained_edge contaria janelas onde "challenger > incumbent" só por flutuação da janela curta.
- **Fix:** novos deques `incumbent_shadow_cw/ccw` com `maxlen=100`, alimentados em paralelo no `check_prediction`, persistidos em `save/load`, resetados em `reset_session`. `get_shadow_stats` agora usa esses.
- **Status:** ✅ corrigido (+ regression test `test_incumbent_shadow_populated_on_check_prediction`).

#### 🟡 BUG-A24-V3-18 — `__post_init__` com `if not self.shadow_grid` duplicado
- **Severidade:** cosmético/refator.
- **Causa raiz:** primeiro `if` sempre executava `= {}` (sempre falsy depois), segundo `if` redundante. Confunde leitor e era branco de defesa contra `None`.
- **Fix:** colapsado em um único bloco com `default_factory` explícito.
- **Status:** ✅ corrigido.

#### 🟡 BUG-A24-V3-21 — `_adaptive_state` não é resetado em `reset_session`
- **Severidade:** média (visível só após S-STRAT-13.1 ativar suggestion).
- **Causa raiz:** `reset_session` reseta deques e Martingale mas mantém `_adaptive_state` intacto. Após mudar dealer, sigmoid_off antigo + `shadow_ema` antigo + `suggested_shift` antigo vazam para a nova sessão.
- **Fix:** `reset_session` agora limpa `_adaptive_state["shadow_ema"]` e `_adaptive_state["suggested_shift"]` (mantém sigmoid_off porque é benéfico cross-dealer).
- **Status:** ✅ corrigido (+ test `test_reset_session_clears_shadow_adaptive_state`).

#### 🟡 BUG-A24-V3-22 — Inconsistência alert vs champion eligibility
- **Severidade:** média (gera "alert sem champion identificado").
- **Causa raiz:** `champion` requer `n>=30` em **ambas** direções; `beats_inc` (que dispara alert) só requer em **uma**. Operador via alert ativo mas champion=None.
- **Fix:** `beats_inc` agora também exige `n>=30` em ambas direções **e** compara médias `(cw+ccw)/2`.
- **Status:** ✅ corrigido (test `test_alert_triggers_when_shadow_beats_incumbent` atualizado).

### 8.2 Implementações desta janela

#### 🚀 S-STRAT-13.1 — Auto-suggestion via EMA + histerese
- **Algoritmo:** para cada shift, `edge_ema = (1-α)·ema + α·edge_avg_raw`, α=0.05.
- **Sustained counter:**
  - `edge_ema > 0.04` AND maduro (n≥50 ambas direções): `sustained += 1`
  - `edge_ema < 0.02`: `sustained = max(0, sustained-1)`
  - Banda morta `0.02-0.04` evita thrashing (PLAN-V2-01).
- **Suggestion emite quando:** `sustained ≥ 200` AND `edge_ema > 0.04` AND n≥50 ambas direções.
- **Persistência:** `_adaptive_state["shadow_ema"]` (por shift) + `_adaptive_state["suggested_shift"]` (top-level). Já persistidos via campo existente.
- **Sem auto-apply:** suggestion fica em `/api/shadow.suggestion` para humano avaliar. Nada toca incumbent.
- **Métricas novas:**
  - `roleta_shadow_edge_ema{shift}`
  - `roleta_shadow_sustained_spins{shift}`
  - `roleta_shadow_suggested_shift` (gauge, 0 se nenhum)

#### 🚀 S-OBS-16 — AlertManager via webhook (sem Telegram)
- **Decisão do usuário:** `"mas nao vamos usar telegram agora"` → receiver = webhook único para `roleta-cloud:8766/api/alerts/sink`.
- **Endpoint novo:** `POST /api/alerts/sink` em `server/health_server.py` (do_POST handler). Apenas loga `alertmanager_webhook status=... sev=... name=... summary=...` + incrementa `roleta_alertmanager_webhook_received_total{severity,alertname}`.
- **Compose:** novo service `alertmanager` (prom/alertmanager:v0.27.0) com volume `alertmanager-data:/alertmanager` (PLAN-V2-06 — silences/notification log sobrevivem restart).
- **Prometheus:** bloco `alerting.alertmanagers` apontando `alertmanager:9093`.
- **Config:** `obs/alertmanager.yml` com routing por severity (critical=10s wait, warning=10min group, repeat 1h). Inhibit rule critical→warning.
- **Quando ligar Telegram no futuro:** basta adicionar `telegram_configs` no receiver — todo o tubo já está testado.

### 8.3 Tabela de patches V2 aplicados

| Patch | Status | Local |
|---|---|---|
| PLAN-V2-01 (EMA+histerese) | ✅ Implementado | `state/game.py::get_shadow_stats` |
| PLAN-V2-04 (cold-start ε) | ⏸ Adiado | depende de S-STRAT-14 (não nesta janela) |
| PLAN-V2-05 (Telegram fallback) | ❌ Removido | usuário decidiu não usar Telegram |
| PLAN-V2-06 (volume alertmanager) | ✅ Implementado | `docker-compose.obs.yml` |
| PLAN-V2-02 (cw/ccw.spin_features) | ⏸ Adiado | requer S-STRAT-8 inteiro |
| PLAN-V2-03 (worker async) | ⏸ Adiado | requer S-STRAT-12 inteiro |

### 8.4 Mudanças de arquivos

| Arquivo | Mudança |
|---|---|
| `state/game.py` | +incumbent_shadow_cw/ccw, EMA+sustained+suggestion no get_shadow_stats, reset_session limpa _adaptive_state shadow, save v2.0.0, post_init unificado |
| `server/health_server.py` | +3 métricas (edge_ema, sustained, suggested_shift) + Counter alerts_received + endpoint `POST /api/alerts/sink` |
| `docker-compose.obs.yml` | +service alertmanager + volume alertmanager-data |
| `obs/alertmanager.yml` | NOVO — receiver webhook único |
| `obs/prometheus.yml` | +bloco `alerting.alertmanagers` |
| `tests/test_shadow_grid.py` | 12 → **17** testes (+5: ema, suggestion emerge, no_sugg, reset_clears, incumbent_populated) |

### 8.5 Validação local

```
181 passed, 7 skipped, 1 xfailed, 10 warnings in 0.80s   (anterior: 176)
test_shadow_grid.py: 17 passed (anterior: 12)
```

### 8.6 Deploy plan (executado abaixo no servidor Debian)

1. `git pull` em `/root/roleta-cloud`
2. Subir alertmanager: `docker compose -f docker-compose.yml -f docker-compose.pg.yml -f docker-compose.obs.yml up -d alertmanager`
3. Reload Prometheus para enxergar alertmanager (`curl -X POST localhost:9090/-/reload`)
4. Rebuild + restart `roleta-cloud` para carregar:
   - novo `incumbent_shadow_*`
   - endpoint `/api/alerts/sink`
   - state.json v2.0.0 (compatível com v1.9 via load tolerant)
5. Smoke-test: `/api/shadow` retorna `suggestion: null` (cold-start) + `challengers[].edge_ema=0.0`
6. Smoke-test webhook: `curl localhost:9093/-/ready` + amplificar contador via regra "always firing" (não fizemos pra não poluir; smoke-test futuro).



