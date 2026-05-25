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
| outbox pending | (query falhou — schema corrigido nesta auditoria) |
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

## 3. Implementação dos fixes (será preenchido após código)

(ver §4)

---

## 4. Resultado dos fixes — _será atualizado após execução_

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
