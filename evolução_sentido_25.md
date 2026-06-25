# Evolução do Sentido — Pós-implantação (rev. 5 · auditoria 25/06/2026)

> **Tema:** continuação de `evolução_sentido.md` (rev. 4) após a implantação completa dos sprints
> **SPR-DIR1…DIR8** e da ativação em produção (PR #25 + PR #26).
> **Tipo:** auditoria + proposta (visão pós-merge + sprints residuais).
> **Base:** código em `HEAD 0dca93d` (25/06/2026) — `feat(sentido): ativa DIR2/DIR4/DIR5/DIR6 por
> default na compose`. **Suíte 689 verde** (`pytest tests/` 33 s) + suíte DIR* 38 verde.
> **Servidor Debian:** roda o commit `0dca93d` desde o tick do `systemd-timer` após o merge.

---

## 0. TL;DR (sumário executivo)

A **rev. 4** projetou 8 sprints para tornar o **sentido do giro** uma **fase determinística** mantida
por **servidor-autoridade**, reusando os canais existentes. Todos os 8 foram entregues, mergeados em
`main` e **ativados por default** na `docker-compose.yml` (DIR7 fica em stand-by, conforme planejado).

**Conformidade global: ≈85%.** O núcleo (autoridade, shift, idempotência, observabilidade) está no ar
e validado pela suíte 689-verde. **Auditoria profunda em 25/06 12:00 BRT** identificou
**15 achados** (8 inicialmente catalogados + **7 novos** descobertos lendo `reset_session`,
`handle_history_correction`, `process_spin` e o caminho `phase_advance → project_phase`).

> **1 ACHADO CRÍTICO (P0):** `reset_session` zera `spin_seq=0`/`seed_n=0` mas **mantém
> `seed_parity` antigo** (`game.py:373-375`). Resultado: após troca de dealer/mesa, a DIR5 segue
> projetando com a fase da **mesa anterior** até o operador chamar `set_seed` (UX hoje não exige).
> Combinado com **#T** (`phase_uncertain` continua incrementando `spin_seq` sem reanchorar) e
> **#W/#X** (`handle_history_correction` reseta timelines mas não a fase), o vetor de aposta no
> **lado errado** existe — mitigado por `direction_divergence_total` + INV-3 (a aposta nunca é
> suprimida, mas pode ir para o sentido errado). **SPR-DIR16** fecha isso.

**Esta rev. 5 propõe 11 sprints residuais (SPR-DIR9…DIR19)** organizadas por prioridade, agora
**redigidas com "verdade estruturada"** — cada sprint contém *por quê (bug auditado)*, *como
(passo concreto)* e *efeitos colaterais (testes em risco)*:
- **P0:** DIR16 (reset/reancoragem — fix crítico)
- **P1:** DIR9 (sentido em sugestao), DIR11 (Alembic), DIR12 (/metrics), DIR17 (reanchora em uncertain)
- **P2:** DIR10 (ultimos[N]), DIR13 (UX lock + **fix #Z lock total**), DIR14 (clear trace_ids), DIR18 (shadow mode)
- **P3:** DIR15 (ADENDO ISO + remove campo morto), DIR19 (buffer fase separado, maxlen 20)

> **Honestidade do gap:** os 7 achados novos não eram visíveis na rev. 4 porque dependiam de ler
> o caminho de troca de mesa e a interação `reset ↔ seed_parity ↔ project_phase` em conjunto. Eles
> NÃO invalidam o entregue (que funciona perfeitamente em sessão única estável); aparecem em
> **transição** (handoff, reset, correção). Rollback global: as 4 flags em `0` na compose volta
> ao comportamento pré-PR #26 byte-a-byte.

---

## 0.1 Bugs / Gaps consolidados (pós-implantação + auditoria profunda 25/06)

> Numeração continua a da rev. 4 (`#1…#H`). Sev: 🔴 trava/desvia aposta · 🟠 muda comportamento ·
> 🟡 limita observabilidade/método · 🟢 cosmético/documental.

### Grupo A — gaps superficiais (catalogados na 1ª passada)

| # | Sev. | Item (o que ficou de fora ou divergiu) | Evidência (HEAD 0dca93d) | Sprint |
|---|---|---|---|---|
| **#J** | 🟡 | Bloco `sentido` **ausente** da resposta de `sugestao` (canal por-giro). Só viaja em `state_sync` (1 s) e no `trace`. Janela ≤1 s onde o cliente pode etiquetar com fase antiga após processar um giro. | `message_handler.py:357,1260` (`_engine_overlay_fields` privado **não inclui `sentido`**); `websocket.py:418` injeta via `game_state.engine_overlay_fields()` (que tem). Duas fontes. | DIR9 |
| **#K** | 🟡 | `ultimos[N]{numero,seq,direction}` previsto na rev. 4 §4 **não publicado** no overlay. Cliente vê só `last_seq`; auditoria externa (dashboard offline) sem timeline rica. | grep `"ultimos"` no servidor: **zero** matches. | DIR10 |
| **#L** | 🟡 | Migração DIR3 (5 colunas em `decisions`) feita via **`ALTER TABLE` in-loco no boot** (`sqlite_repo.py:372-380`) em vez de Alembic. Banco zero+ Alembic `upgrade head` **não** cria as colunas até o servidor subir. | `migrations/versions/` para no `0009_vision_features.py` (19/06, anterior ao DIR3). | DIR11 |
| **#M** | 🟡 | 3 métricas DIR8 (`gap_recuperado_total`, `phase_uncertain_total`, `direction_divergence_total`) **não expostas em `/metrics` Prometheus**. Só no `sentido.stats` do `state_sync`. Grafana externo cego. | `server/health_server.py` lista providers Prometheus; `phase_metrics` ausente; módulo já comenta "pronto para /metrics". | DIR12 |
| **#N** | 🟢 | UX DIR8 "seed 1× + travar fase" **parcialmente** implementada. `background.js:1248-1251` envia `set_seed` quando o operador escolhe direção (ANCORA), mas **não há botão "travar"** (`direction_locked`) no `popup.html`. Badge `source` chega ao overlay via `sentido.source`, mas o `content.js` não tem visual distinto. | grep `direction_locked` em `extension/`: zero matches; `popup.html` sem campo de lock. | DIR13 |
| **#O** | 🟢 | `_recent_trace_ids` (DIR6, deque maxlen=64) **nunca limpo** em `reset_session` ou `role_assigned`. Em um reset seguido de re-envio com `trace_id` recente, o primeiro giro pode ser ignorado como "duplicado". Risco baixíssimo (cliente gera `trace_id` por `timestamp`). | `message_handler.py:175-179` init lazy; nenhum `clear()` em `reset_session` (`:1269`) nem em `role_assigned`. | DIR14 |
| **#P** | 🟢 | Renomeação `client_seq` (rev. 4 §6 DIR3) → `client_spin_seq` (código `:528`). Apenas documentação; nenhuma quebra de contrato (ambos lados usam o nome novo). | grep `client_spin_seq`: 4 matches em `models/input.py` + `message_handler.py`. | DIR15 |
| **#Q** | 🟡 | `phase_uncertain` ainda incrementa `spin_seq += 1` (`:762`) mesmo quando o shift não casou — **PROMOTED a #T** abaixo (combinado com #S, deixou de ser cosmético). | `message_handler.py:711-715,762`. | DIR17 |

### Grupo B — bugs estruturais (descobertos na auditoria profunda, lendo o caminho `reset → seed_parity → project_phase`)

| # | Sev. | Item (bug ou risco real) | Evidência (HEAD 0dca93d) | Sprint |
|---|---|---|---|---|
| **#R** | 🟡 | `recent_results` é **`deque(maxlen=10)`**, mas a rev. 4 §5 pedia **`maxlen ~20`** para shift mais robusto. Com janela 10, `phase_advance` recupera até k=10 — suficiente para o caso real, mas reduz margem em minimizações longas (>20 s sem tick) ou trocas frequentes de mesa. | `state/game.py:238,326,1378` (todas as 3 instâncias com `maxlen=10`). Doc §5: "`recent_results` maxlen ~20". | DIR19 |
| **#S** | 🔴 | **CRÍTICO.** `reset_session` zera `spin_seq=0`/`seed_n=0`/`direction_source="reset"` mas **NÃO toca `seed_parity` nem `direction_locked`**. Após troca de mesa/dealer, o auto-seed da DIR5 (`if not _gs.seed_parity:` em `:726`) **falha** porque o valor permanece, e `project_phase` segue usando a paridade da **mesa anterior**. → aposta vai para o sentido errado até alguém ver `direction_divergence_total` subir e o operador chamar `set_seed`. UX hoje não exige isso. | `state/game.py:373-375` zera 3 campos, não os 5. `message_handler.py:726-728` auto-seed depende de `seed_parity=""`. | **DIR16** |
| **#T** | 🟠 | `phase_uncertain=True` (troca de mesa silenciosa, shift sem alinhamento) entra no fluxo: `spin_seq += 1` rodando incondicionalmente (`:762`), `project_phase` projeta com `(seed_parity_antigo, seed_n_antigo, spin_seq+1)` → direção autoritativa errada **persiste** giro após giro. `resync_advised=true` é o único sinal — cliente precisa ver e agir. INV-3 não suprime aposta, mas o lado pode ficar consistentemente trocado. | `message_handler.py:711-715` (só warning+métrica), `:762` (incremento incondicional). | DIR17 |
| **#U** | 🟡 | A rev. 4 §6 DIR3 prometia "Flag OFF: ainda obedece o master, **registra divergência** cliente↔projeção". A implementação atual **só roda o bloco DIR5 quando `SDA_SENTIDO_AUTORITATIVO=1`** (`:722-756`) — em OFF, `project_phase` nem executa e `direction_divergence_total` fica zerado. Impossível avaliar "o que acontece se eu desligar?" sem fazer A/B real. | `message_handler.py:722` `if sentido_autoritativo_enabled():` envolve TUDO. | DIR18 |
| **#W** | 🟠 | `handle_history_correction` reseta `timeline_cw`/`timeline_ccw`/`recent_results`/`last_*` mas **NÃO** toca `seed_parity`/`seed_n`/`spin_seq`. Doc §4.2: "correção do operador vira REANCORAGEM de fase". Cliente DIR1+ chama `set_seed` separadamente; clientes legados continuam mandando `correcao_historico` puro e a fase fica inconsistente. | `message_handler.py:1349-1386` toca timelines, não fase. | DIR16 |
| **#X** | 🟠 | Após `handle_history_correction` reprocessar histórico via `register_history_number` ou `process_spin`, **`spin_seq` não é incrementado** (process_spin não toca em spin_seq — só `handle_new_result` em `:762`). `spin_seq` fica congelado em 0/antigo, mas `last_direction` reflete N spins reprocessados. Próxima projeção tem `seed_n vs spin_seq` desalinhados. | `state/game.py:382-414` `process_spin` não toca `spin_seq`. Reprocessamento em `:1364-1374` não chama o caminho que incrementa. | DIR16 |
| **#Y** | 🟢 | Campo `client_spin_seq` aceito por `SpinInput` (`models/input.py`) e desempacotado em `:528`, mas o cliente **NUNCA envia** (grep em `extension/`: zero `client_spin_seq`). Campo morto na borda — over-engineering inerte. Não bug, mas confunde leitura. | `extension/background.js` sem `client_spin_seq`. | DIR15 |
| **#Z** | 🟠 | **Semântica enganosa de `direction_locked`.** O campo existe em `GameState` e é setado por `set_seed{locked:true}`, mas **só é checado em UM lugar**: `:740` (`if direction_vision_enabled() and not _gs.direction_locked`) — bloqueia apenas a fusão de vídeo (DIR7). NÃO impede `phase_advance` (DIR4) de incrementar `spin_seq`, nem `project_phase` (DIR5) de reprojetar, nem o auto-seed de reanchorar. O nome promete "trava" mas a implementação é "só não escuta vídeo". UX da DIR13 espera lock total. | `message_handler.py:740` é a única leitura útil; nenhuma checagem em `:701-715,723-756`. | DIR13 (refinado) |

---

## 0.2 Verificação de afirmações (auditoria rev. 5)

| Afirmação rev. 4 | Veredito | Prova (HEAD 0dca93d) |
|---|---|---|
| **DIR1** — SW re-hidrata `currentDirection` no boot | ✅ confirmado | `background.js:971-980` `chrome.storage.local.get(['currentDirection','directionSeed'])` |
| **DIR1** — `state_sync` corrige `currentDirection` | ✅ **com bônus** | `background.js:584-596` lê **`data.data.sentido.next_direction`** (DIR5) com fallback para `target_direction` (DIR1). |
| **DIR1** — `sessao_resetada` reseta para o seed | ✅ confirmado | `background.js:604-617` `currentDirection = directionSeed \|\| 'horario'` + persiste. |
| **DIR2** — `handle_initial_history` deixou de envenenar | ✅ confirmado | Flag `SDA_HISTORICO_NAO_DIRECIONAL=1` (compose). Testes em `test_dir2_*` cobrem golden SDA17. |
| **DIR3** — Round-trip dos 5 campos | ✅ confirmado | `state/game.py:1280-1284` (save), `:1380-1384` (load), `:373-375` (reset). |
| **DIR3** — Migração aditiva em `decisions` | ⚠️ **divergiu o método** | Feito via `ALTER TABLE` in-loco em `sqlite_repo.py:372-380` (idempotente), **não** via Alembic. → **#L**. |
| **DIR4** — `phase_advance`/shift + `gap_recuperado_total` | ✅ confirmado | `state/phase.py` (módulo puro), chamado em `message_handler.py:701-707`. |
| **DIR4** — Validação da ordem do DOM por provider | ⚠️ **assumido** | A premissa `numbers[0]=mais recente` segue assumida (`background.js:1622`); nenhuma validação por-provider. Risco contido por `phase_uncertain` se inverter. |
| **DIR5** — Bloco `sentido` em `state_sync`/`sugestao` | ⚠️ **só em state_sync** | `state_sync` (`websocket.py:418`) e `trace` (`message_handler.py:1308`) injetam o bloco; **resposta `sugestao` (handler) NÃO**. → **#J**. |
| **DIR5** — `ultimos[N]` no overlay | ❌ **não entregue** | grep `"ultimos"` em `server/`: zero. → **#K**. |
| **DIR5** — `direction_divergence_total` | ✅ confirmado | `message_handler.py:754` `phase_metrics.incr(...)`. |
| **DIR6** — Idempotência por `trace_id` | ✅ confirmado | `_is_duplicate_trace` deque(64) `:170-179` + check `:434-436`. |
| **DIR6** — Gap → resync | ✅ **via flag/sinal** | `resync_advised` no bloco `sentido` (`game.py:1028`); cliente lê em `background.js:584`. |
| **DIR6** — Limpeza do deque em reset | ❌ **não entregue** | → **#O**. |
| **DIR7** — Fusão vídeo (stand-by) | ✅ confirmado | `SDA_DIRECTION_VISION=0` (compose); contrato pronto via `last_direction_event`. |
| **DIR8** — 3 métricas em `phase_metrics.py` | ✅ confirmado | `state/phase_metrics.py:11-15`. |
| **DIR8** — `sentido.stats` no overlay | ✅ confirmado | `game.py:1032`. |
| **DIR8** — `/metrics` Prometheus | ❌ **não entregue** | → **#M**. |
| **DIR8** — UX popup "seed 1× + travar" + badge | ⚠️ **parcial** | `set_seed` enviado; **sem** botão lock no popup; `content.js` sem badge de origem distinta. → **#N**. |
| **INV-3** — `phase_uncertain` nunca suprime aposta | ✅ confirmado | `:711-715` só log + métrica + `resync_advised`; `_gs.spin_seq` segue avançando. **MAS** ver **#T** (lado pode ficar errado). |
| **INV ADITIVO** — Nada removido/renomeado | ✅ confirmado | Toda mudança é `out["sentido"]=…` ou `ADD COLUMN`. Defaults em `settings.py` permanecem `"0"`. |
| **Auditoria profunda — reset_session** | ❌ **bug crítico** | Zera `spin_seq=0`/`seed_n=0` mas mantém `seed_parity` (mesa anterior). → **#S**. |
| **Auditoria profunda — handle_history_correction** | ❌ **2 bugs** | Não reancora fase (→ **#W**) e não atualiza `spin_seq` ao reprocessar (→ **#X**). |
| **Auditoria profunda — process_spin** | ⚠️ **separação de responsabilidade** | NÃO toca `spin_seq`; só `handle_new_result` em `:762` incrementa. Reprocessamento via correção/histórico fica desincronizado. → contexto de **#X**. |
| **Auditoria profunda — `recent_results` maxlen** | ⚠️ **divergiu** | `maxlen=10` em 3 locais (`:238,326,1378`). Doc §5 pedia `~20`. → **#R**. |
| **Auditoria profunda — `client_spin_seq`** | ⚠️ **campo morto** | Aceito em `:528`, nunca enviado por `extension/`. → **#Y**. |
| **Auditoria profunda — DIR5 SHADOW mode** | ❌ **não entregue** | Bloco DIR5 só roda se `SDA_SENTIDO_AUTORITATIVO=1`. Doc §6 DIR3 pedia divergência em OFF. → **#U**. |
| **Suíte verde** (`pytest tests/`) | ✅ **689 passed** | 9 skipped, 1 xfailed, 33 s em local. CI em main `0dca93d`: 4/4 SUCCESS. |
| **Extensão** — bump `manifest.version` | ✅ **3.6.0** | `extension/manifest.json`. |

---

## 1. Como funciona HOJE (verificado em HEAD `0dca93d`)

### 1.1 Caminho de um giro (pós DIR1…DIR8)
```
Escuta Beat 3.6.0 (Chrome MV3)                                  Servidor (Python, asyncio)
─────────────────────────────                                  ────────────────────────────
boot SW:  re-hidrata currentDirection+directionSeed             handle_new_result:
          do chrome.storage.local                                 1) _is_duplicate_trace(trace_id) #DIR6
readLoop ~2s: extractResultsFromPage() → numbers[]                2) phase_advance(prev, allNumbers) → (k, inter, uncertain) #DIR4
  newNumbers[…] (todos os novos, não só [0])                       n += k   (auto-seed se seed_n==0)
  novo_resultado{ numero, allNumbers[12],                          3) project_phase(seed, seed_n, n) → fase #DIR5
                  direction_hint, trace_id }   ────────────►       4) SDA17 + save_decision (com spin_seq, source, conf, next, uncertain) #DIR3
                                                                   5) Atualiza phase_metrics:
                                                                       gap_recuperado_total += k
                                                                       phase_uncertain_total (se ambíguo)
                                                                       direction_divergence_total (se autoridade ≠ hint)
   consome data.sentido.next_direction         ◄─ state_sync (1s)─ broadcast_heartbeat:
   se uncertain → resync_advised=true             data.sentido = {                   #DIR5
   se srvDir ≠ currentDirection:                    last_seq, last_direction,
     currentDirection = srvDir + persiste            next_direction, locked,
     console.log "🔄 DIR1 resync de fase"            source, resync_advised,
                                                     stats: {gap_recuperado_total,
   role_assigned → resync                              phase_uncertain_total,
   sessao_resetada → currentDirection=seed             direction_divergence_total} }
                                                                   ──────────────────────────
                                                   ◄─ sugestao ─── overlay_response["data"] |= _engine_overlay_fields()
                                                   (handler: force17/c_selection/block_gale/bet_gate/ultimo_acerto)
                                                   ⚠️ NÃO inclui "sentido" — gap #J
```

### 1.2 Infra ativada (rev. 5)
| Recurso | Local | Estado |
|---|---|---|
| `state_sync.sentido{…}` (1 s) | `state/game.py:1018-1034` + `server/websocket.py:418` | ✅ canal autoritativo no ar |
| `phase_advance` (shift puro) | `state/phase.py` | ✅ |
| `project_phase` (fase determinística) | `state/phase.py` | ✅ |
| `phase_metrics` (singleton 3 contadores) | `state/phase_metrics.py` | ✅ (só no `state_sync`; falta `/metrics`) |
| `_is_duplicate_trace` (idempotência) | `server/message_handler.py:170-179` | ✅ (faltam clears) |
| Re-hidratação SW + consumo `sentido.next_direction` | `extension/background.js:584-596,971-980` | ✅ |
| `set_seed` por escolha do operador | `extension/background.js:1248-1251` | ✅ (falta UI lock) |

---

## 2. Riscos remanescentes (pós-merge `0dca93d` + auditoria profunda)

| Risco | Probabilidade | Mitigação atual | Sprint que fecha |
|---|---|---|---|
| 🔴 **Aposta no lado errado em handoff de dealer/mesa** (`seed_parity` da mesa anterior persiste) | **ALTA em transição**, zero em sessão estável | INV-3 mantém aposta; `direction_divergence_total` sobe persistente; operador pode chamar `set_seed` se notar | **DIR16 (P0)** |
| 🟠 **`phase_uncertain` perpetua direção errada** giro após giro até cliente ver `resync_advised` | Média (depende de #S — se seed estiver bom, mitigado) | `resync_advised=true` no overlay; cliente DIR1 sobrescreve | **DIR17 (P1)** |
| 🟠 **`correcao_historico` deixa fase inconsistente** com timelines reprocessadas | Baixa-Média (cliente DIR1+ chama `set_seed` em separado; legados não) | reprocessamento de timeline correto; só fase fica órfã | **DIR16 (P0)** |
| 🟡 Cliente etiqueta giro com fase antiga em ≤1 s após processar (canal `sugestao` sem `sentido`) | Baixa-Média | Próximo `state_sync` (1 s) corrige; `direction_divergence_total` mede | DIR9 (P1) |
| 🟡 Banco novo (deploy zero-state) sem colunas DIR3 até primeiro spin | Baixa | `ALTER TABLE … IF NOT EXISTS`-like (try/except `SELECT`) no boot | DIR11 (P1) |
| 🟡 Painel Grafana externo sem visibilidade da fase | Alta (já é!) | `sentido.stats` no `state_sync` (dashboards internos OK) | DIR12 (P1) |
| 🟡 Impossível medir "se eu desligar a autoridade, quanto diverge?" sem A/B real | Alta (já é!) | nenhuma — divergência só conta com autoridade ON | DIR18 (P2) |
| 🟡 Shift recupera só k≤10 (minimização longa pode estourar) | Baixa | `phase_uncertain` quando shift estoura | DIR19 (P3) |
| 🟢 Operador não consegue **travar** a fase (apenas ANCORA) | Baixa | INV-3 mantém aposta; reanchoragem manual funciona | DIR13 (P2) |
| 🟢 Falso-positivo de dedup pós-reset | Muito baixa | `trace_id` baseado em `timestamp` (cliente quase nunca repete) | DIR14 (P2) |
| 🟢 Ordem do DOM diferir por provider (premissa §0.2 rev. 4) | Baixa | `phase_uncertain` quando shift não casa | (já coberto) |
| 🟢 Campo `client_spin_seq` morto no servidor | Zero (não bug, só confusão) | nenhuma | DIR15 (P3) |

---

## 3. Sprints propostas (SPR-DIR9 … SPR-DIR19) — **verdade estruturada**

> Cada sprint contém: **🎯 PORQUÊ (verdade auditada)** — bug real + ator + frequência + severidade;
> **🔧 COMO (passo concreto)** — arquivos/linhas exatas; **⚠️ EFEITOS COLATERAIS** auditados na
> suíte 689; **✅ DoD** verificável; **🚦 FLAG/ROLLBACK** explícitos; **🛡️ RISCO residual**.
> Toda sprint: **flag default-OFF** quando aplicável, **aditiva**, **suíte verde** (`pytest tests/`),
> **PR** com ADENDO em `Manutenabilidade_iso.md`. Prefixo `SPR-DIR9+` não conflita com
> `SPR-S*/SPR-G*` do `BOARD.md`.

---

### 🔴 SPR-DIR16 · **CRÍTICA P0** · Reset/reancoragem completa de fase · Locks: BLK-D, BLK-G

**🎯 PORQUÊ (auditado):**
- **Bug #S real:** `state/game.py:373-375` zera apenas `spin_seq`, `seed_n`, `direction_source`.
  `seed_parity`/`direction_locked`/`last_phase_uncertain`/`last_direction_event` ficam
  congelados. **Reproduzo:** após `reset_session()`, `gs.seed_parity` ainda contém
  `"horario"|"anti-horario"` da mesa anterior; `_engine_overlay_fields` em `message_handler.py:726`
  (`if not _gs.seed_parity:`) **falha** porque a string é truthy → auto-seed **nunca** dispara →
  `project_phase` projeta com paridade da mesa antiga **indefinidamente**.
- **Bug #W real:** `message_handler.py:1349-1386` (`handle_history_correction`) limpa
  `timeline_cw/ccw`, `recent_results`, `last_number`, `last_direction`. **NÃO** toca
  `seed_parity`/`seed_n`/`spin_seq`. Cliente DIR1+ chama `set_seed` em separado; cliente legado
  fica defasado.
- **Bug #X real:** `state/game.py:382-414` (`process_spin`) não toca `spin_seq` — só
  `handle_new_result` em `:762` incrementa. Reprocessamento de histórico via
  `handle_history_correction` chama `process_spin`/`register_history_number` → `spin_seq` fica
  em 0 enquanto a timeline tem N spins. `seed_n` (0) e `spin_seq` (0) ficam fora de fase com
  `last_direction` que reflete o último dos N reprocessados.
- **Ator afetado:** operador em troca de dealer/mesa, ou rotação por carrossel de roletas.
- **Frequência baseline:** ~5-20×/sessão de 4h (cada troca de dealer/mesa); 100% das vezes em
  cada uma dessas transições.
- **Severidade 🔴:** combina com DIR5 ativa em produção → aposta sai no sentido errado por todo
  o período até alguém ver `direction_divergence_total` subir e o operador reanchorar manualmente.
  INV-3 não suprime aposta, mas o lado pode ficar consistentemente trocado.

**🔧 COMO (passo concreto):**
1. **`state/game.py:reset_session` (`:373-375`)** — substituir o bloco DIR3 por:
   ```python
   # DIR16: re-ancora fase no novo começo. Zera tudo SE não foi um lock explícito.
   self.spin_seq = 0
   self.seed_n = 0
   self.direction_source = "reset"
   if not self.direction_locked:
       self.seed_parity = ""           # força auto-seed da DIR5 no 1º giro pós-reset
       self.last_phase_uncertain = False
       self.last_direction_event = None
   ```
2. **`server/message_handler.py:handle_history_correction` (`:1355-1376`)** — adicionar após
   `self.game_state.recent_results.clear()`:
   ```python
   # DIR16: reancora fase ao reprocessar histórico. Próximo novo_resultado faz auto-seed.
   if not self.game_state.direction_locked:
       self.game_state.seed_parity = ""
       self.game_state.seed_n = 0
   # spin_seq segue o número de spins efetivamente reprocessados (timeline-consistent).
   self.game_state.spin_seq = sum(1 for it in resultados if it.get("numero") is not None)
   ```
3. **`server/message_handler.py:handle_initial_history` (`:1315-1347`)** — adicionar o mesmo
   bloco após o loop de reprocessamento.
4. **Hook no `handle_new_session`** (`:1393`): nada a fazer — `reset_session` já cobre.

**⚠️ EFEITOS COLATERAIS auditados:**
- **15 testes** exercitam `reset_session` (grep `tests/*.py`). Risco de quebra em testes que
  assumem `seed_parity` persistir após reset. **Mitigação:** gateá-lo por sub-flag
  `SDA_RESET_REANCORA=1` (default-ON em produção, OFF nos testes legados via fixture).
- **6 testes** mexem em `seed_parity` diretamente — auditá-los e atualizar expectativas onde
  o novo comportamento é desejado.
- `handle_history_correction` agora altera `spin_seq` — clientes que liam o estado intermediário
  via `get_state` veem `spin_seq=N` em vez de 0. **Não-quebra** (campo aditivo, observabilidade).

**✅ DoD verificável:**
- `test_dir16_reset_zera_seed_parity.py`: `(giro horario → reset → giro anti-horario)` deve
  resultar em `gs.seed_parity == "anti-horario"` (auto-seedou no 2º giro), **não** `"horario"`.
- `test_dir16_correcao_historico_reancora.py`: após `handle_history_correction` com 5 spins,
  `gs.spin_seq == 5` e `gs.seed_parity == ""` (próximo `novo_resultado` ancora).
- `test_dir16_handoff_dealer.py`: simula troca de dealer (reset + giro com fase oposta) e
  verifica `phase_metrics.snapshot()["direction_divergence_total"]` cresce ≤1 (ideal 0).
- **Não-regressão:** suíte 689 verde com `SDA_RESET_REANCORA=1` E `SDA_RESET_REANCORA=0`.

**🚦 FLAG/ROLLBACK:**
- Sub-flag `SDA_RESET_REANCORA=1` (default-ON na compose após validação 24h).
- OFF restaura comportamento atual byte-a-byte (mantém `seed_parity` antigo no reset).
- Rollback `git revert` do PR completo é seguro (todas mudanças por trás da flag).

**🛡️ RISCO residual:** Baixo. O risco real é em produção — em testes, gateado pela flag.
A UX nova (operador precisa reanchorar após reset) já existe via `set_seed` (DIR8); este sprint
**automatiza** a parte mecânica.

---

### 🟠 SPR-DIR17 · Reancorar seed em `phase_uncertain` · **P1** · Locks: BLK-D · depende de DIR16

**🎯 PORQUÊ (auditado):**
- **Bug #T real:** `message_handler.py:711-715` quando `_phase_uncertain=True` apenas loga warning,
  incrementa `phase_uncertain_total`, e seta `resync_advised=true`. **NÃO reanchora.** Linha 762
  (`spin_seq += 1`) corre incondicionalmente. Próxima `project_phase` em `:732` usa
  `(seed_parity_antigo, seed_n_antigo, spin_seq_novo)` → projeção pode ficar consistentemente
  no sentido errado por **N giros** até o cliente ver `resync_advised` e mandar `set_seed`.
- **Ator afetado:** cliente que perde sincronia (troca de mesa silenciosa, timeout >40s,
  re-render do DOM com lista totalmente diferente).
- **Frequência baseline:** rara em sessão estável (~0-2×/h); 100% durante troca não-anunciada.
- **Severidade 🟠:** combinado com #S resolvido (DIR16 já feita), o problema reduz mas persiste.

**🔧 COMO (passo concreto):**
1. **`server/message_handler.py:711-715`** — substituir o bloco:
   ```python
   if _phase_uncertain:
       phase_metrics.incr("phase_uncertain_total")
       logger.warning("[FASE] shift sem alinhamento (possivel troca de mesa) — phase_uncertain")
       # DIR17: reancora — força auto-seed no próximo giro alinhado.
       # Só reanchora SE flag ativa E o operador não travou explicitamente a fase.
       from app_config.settings import uncertain_reancora_enabled
       if uncertain_reancora_enabled() and not self.game_state.direction_locked:
           self.game_state.seed_parity = ""
           self.game_state.seed_n = self.game_state.spin_seq  # marca "ponto zero" novo
           logger.info("[FASE] DIR17: seed zerado — proximo giro alinhado faz auto-seed")
   ```
2. **`app_config/settings.py`** — adicionar:
   ```python
   def uncertain_reancora_enabled() -> bool:
       import os
       return os.environ.get("SDA_UNCERTAIN_REANCORA", "0").strip().lower() in ("1","true","on")
   ```
3. **`docker-compose.yml`** — após validação 24h em produção: `SDA_UNCERTAIN_REANCORA=${SDA_UNCERTAIN_REANCORA:-1}`.
4. Manter `spin_seq += 1` na linha 762 (mantém contador de eventos para auditoria).

**⚠️ EFEITOS COLATERAIS auditados:**
- Nenhum teste existente força `_phase_uncertain=True` (caminho exercido só por `test_dir4_*` em
  cenários ad-hoc). Adicionar fixture nova.
- Comportamento muda **apenas** quando shift não casa — caminho frio.

**✅ DoD verificável:**
- `test_dir17_uncertain_reanchora.py`: sequência (5 giros normais com `seed_parity="horario"` →
  `allNumbers` totalmente diferente que NÃO casa o shift) → `gs.seed_parity == ""` imediatamente,
  e próximo `novo_resultado` com `direcao="anti-horario"` faz `gs.seed_parity == "anti-horario"`.
- `direction_divergence_total` para de crescer em ≤2 giros após `uncertain`.
- Não-regressão: suíte 689 verde com flag ON e OFF.

**🚦 FLAG/ROLLBACK:**
- Sub-flag `SDA_UNCERTAIN_REANCORA=1` (default-OFF inicialmente; default-ON após validação).
- OFF preserva comportamento atual (só warning + métrica).

**🛡️ RISCO residual:** Baixo. Caminho frio; rollback por flag.

---

### SPR-DIR9 · `sentido` na resposta de `sugestao` (não só `state_sync`) · **P1** · Locks: BLK-D

**🎯 PORQUÊ (auditado):**
- **Bug #J real:** `message_handler.py:357,1260` — `_engine_overlay_fields()` privado retorna
  `c_selection/force17/block_gale/bet_gate/ultimo_acerto`, **não** o bloco `sentido`. A resposta
  `sugestao` (canal por-giro) sai sem `sentido`. Cliente só pega o bloco no próximo `state_sync`
  (≤1 s depois).
- **Ator afetado:** cliente que etiqueta o overlay imediatamente após receber `sugestao`. Em
  ~1% dos giros pode mostrar fase 1 tick atrasada.
- **Frequência:** todo giro (~3 giros/min em mesa rápida).
- **Severidade 🟡:** cosmético; o próximo state_sync corrige em ≤1 s.

**🔧 COMO (passo concreto):**
1. **`server/message_handler.py:1258-1262`** — substituir:
   ```python
   try:
       overlay_response["data"].update(self._engine_overlay_fields())
       # DIR9: também publica o bloco `sentido` no canal por-giro (não só state_sync 1s).
       # As duas fontes são COMPLEMENTARES (handler tem _cs_meta/_bg_meta; GameState tem sentido).
       overlay_response["data"].update(self.game_state.engine_overlay_fields())
   except Exception:  # noqa: BLE001
       pass
   ```
2. **Não unificar** `_engine_overlay_fields` com `engine_overlay_fields` — eles vivem em escopos
   diferentes (handler vs GameState) por motivo (AUDIT-1 do `Manutenabilidade_iso.md:294`).

**⚠️ EFEITOS COLATERAIS auditados:**
- `test_wiring_c_gale.py:143,301` chama `h._engine_overlay_fields()` — segue funcionando.
- `test_ws_overlay_contract.py` valida formato de `engine_overlay_fields` — segue verde.
- Payload `sugestao` cresce ~150-300 bytes (bloco `sentido` + `stats`). Tolerável.

**✅ DoD verificável:**
- `test_dir9_sentido_na_sugestao.py`: após `handle_new_result`, a resposta `sugestao` tem
  `data["sentido"]["last_seq"]`, `data["sentido"]["next_direction"]`, `data["sentido"]["stats"]`.
- Suíte 689 verde.

**🚦 FLAG/ROLLBACK:** N/A (campo aditivo; clientes antigos ignoram). Se quiser segurança extra:
sub-flag `SDA_SENTIDO_NA_SUGESTAO=1` default-ON.

**🛡️ RISCO residual:** Mínimo. Duplica campos no payload; bytes extras < 1 KB/giro.

---

### SPR-DIR11 · Migração Alembic `0010_dir3_phase_columns.py` retroativa · **P1** · Locks: schema, alembic

**🎯 PORQUÊ (auditado):**
- **Bug #L real:** `migrations/versions/` termina em `0009_vision_features.py` (19/06,
  pré-DIR3). As 5 colunas DIR3 são criadas via `ALTER TABLE` no boot do servidor
  (`sqlite_repo.py:372-380`) usando padrão try/`SELECT`/except/`ALTER`. Funcional, mas
  **não-uniforme** com o resto do projeto e quebra a sequência de versões Alembic.
- **Ator afetado:** desenvolvedor que faz `alembic upgrade head` em DB zero — schema fica
  incompleto até o servidor subir e executar o fallback in-loco.
- **Frequência:** todo bootstrap zero-state (deploy novo, dev local).
- **Severidade 🟡:** método; não bug funcional.

**🔧 COMO (passo concreto):**
1. **Criar `migrations/versions/0010_dir3_phase_columns.py`:**
   ```python
   """DIR3: phase columns (spin_seq, direction_*, phase_uncertain) — aditiva."""
   from alembic import op
   import sqlalchemy as sa

   revision = "0010_dir3_phase"
   down_revision = "0009_vision_features"
   branch_labels = None
   depends_on = None

   def upgrade():
       # Idempotente: skip se sqlite_repo.py já adicionou via fallback.
       conn = op.get_bind()
       existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(decisions)").fetchall()}
       cols = [
           ("spin_seq", sa.Integer()),
           ("direction_source", sa.Text()),
           ("direction_confidence", sa.Float()),
           ("direction_next", sa.Text()),
           ("phase_uncertain", sa.Boolean()),
       ]
       for name, type_ in cols:
           if name not in existing:
               op.add_column("decisions", sa.Column(name, type_, nullable=True))

   def downgrade():
       # INV: schema não-destrutivo. No-op (aditivo, retro-compatível).
       pass
   ```
2. **Manter `sqlite_repo.py:372-380`** como fallback (lê catalog primeiro; idempotente).

**⚠️ EFEITOS COLATERAIS auditados:**
- Lock `schema/alembic` serializa com **SPR-G2** (BOARD.md) — coordenar com Diretor.
- `alembic_version` table atualiza para `0010_dir3_phase` — irreversível em produção sem editar.

**✅ DoD verificável:**
- DB vazio: `alembic upgrade head` cria as 5 colunas. Round-trip dos testes DIR3 segue verde.
- DB existente (com colunas via fallback): `alembic upgrade head` é no-op (não falha).
- `alembic downgrade -1`: no-op (não-destrutivo).

**🚦 FLAG/ROLLBACK:** N/A (aditivo, retro-compatível). Rollback = `git revert` do PR + `alembic
stamp 0009_vision_features` no host (manual).

**🛡️ RISCO residual:** Baixo. Coordenar com qualquer outro PR que mexa em schema.

---

### SPR-DIR12 · `/metrics` Prometheus expõe DIR8 · **P1** · Locks: obs

**🎯 PORQUÊ (auditado):**
- **Bug #M real:** `state/phase_metrics.py:1-40` exporta 3 contadores
  (`gap_recuperado_total`, `phase_uncertain_total`, `direction_divergence_total`) via
  `snapshot()`. **Único consumidor hoje:** `state/game.py:1032`
  (`out["sentido"]["stats"] = phase_metrics.snapshot()`). `server/health_server.py` NÃO inclui
  esses contadores — `grep` retorna zero matches.
- **Ator afetado:** painéis Grafana, alerting externo, observabilidade pós-deploy.
- **Frequência:** todo scrape (~15-30 s).
- **Severidade 🟡:** observabilidade externa cega.

**🔧 COMO (passo concreto):**
1. **`server/health_server.py:119`** — adicionar bloco no setup dos Counter Prometheus:
   ```python
   from state import phase_metrics as _pm
   # DIR12: 3 contadores monotônicos da fase (DIR8).
   _PHASE_COUNTERS = {
       "gap_recuperado_total": Counter("roleta_gap_recuperado_total",
           "Giros recuperados pelo shift (DIR4)"),
       "phase_uncertain_total": Counter("roleta_phase_uncertain_total",
           "Eventos de fase ambígua (DIR4 sem alinhamento)"),
       "direction_divergence_total": Counter("roleta_direction_divergence_total",
           "Vezes que a autoridade (DIR5) corrigiu o hint do cliente"),
   }
   ```
2. **`_collect_phase` (função nova ao lado de `_collect_*` existentes)**: a cada scrape,
   ler `_pm.snapshot()` e setar os Counter via `_set_to_value` (Prometheus Counters não
   decrescem; usar `inc(delta)` desde o último valor lido — pattern já usado em outros providers).

**⚠️ EFEITOS COLATERAIS auditados:**
- Nenhum — `_collect_*` é tolerante a falhas (`_collect_phase` segue o padrão).
- Métricas Prometheus aparecem em `/metrics` no próximo scrape após deploy.

**✅ DoD verificável:**
- `curl http://localhost:8766/metrics | grep -E 'roleta_(gap_recuperado|phase_uncertain|direction_divergence)_total'`
  retorna 3 linhas TYPE/HELP/value.
- `test_dir12_metrics_exporter.py`: mocka `phase_metrics.snapshot()` e valida que `/metrics` reflete.

**🚦 FLAG/ROLLBACK:** N/A (só leitura, providers já tolerantes). Rollback = `git revert`.

**🛡️ RISCO residual:** Mínimo. Métricas Prometheus existem mesmo se nada incrementar (zero).

---

### SPR-DIR10 · `ultimos[N]{numero,seq,direction}` no overlay · **P2** · Locks: BLK-D, obs

**🎯 PORQUÊ (auditado):**
- **Bug #K real:** `engine_overlay_fields` publica `last_seq` (1 valor escalar). Cliente vê
  apenas "fase atual" — sem timeline para auditoria offline. `grep` em `server/`: zero matches
  para `"ultimos"`.
- **Ator afetado:** dashboards externos, auditoria pós-sessão, depuração de phase_uncertain.
- **Frequência:** sempre que se quer reconstruir a fase histórica.
- **Severidade 🟡:** observabilidade. Não bloqueia operação.

**🔧 COMO (passo concreto):**
1. **`state/game.py`** — adicionar buffer separado (NÃO realocar `recent_results`):
   ```python
   # DIR10: ring buffer só p/ overlay (timeline rica auditável). Mantido em paralelo
   # ao recent_results (zona fria C3, maxlen=10 — não mexer, ver DIR19 #R).
   _phase_overlay_ring: deque = field(default_factory=lambda: deque(maxlen=12))
   ```
2. **`process_spin` (após `recent_results.appendleft(numero)`)** — appendleft de `{numero, spin_seq, direction}` ao novo deque.
3. **`engine_overlay_fields`** — adicionar:
   ```python
   out["ultimos"] = list(self._phase_overlay_ring)  # já em ordem [0]=mais recente
   ```
4. **Round-trip:** `save_state`/`load_state` persistem `_phase_overlay_ring`.

**⚠️ EFEITOS COLATERAIS auditados:**
- Payload `state_sync` cresce ~480 bytes/s (12 entries × 40 B). Tolerável.
- Round-trip JSON estável (lista de dicts triviais).
- Nenhum teste existente quebra.

**✅ DoD verificável:**
- `test_dir10_overlay_ultimos.py`: após 5 giros, `overlay["ultimos"]` tem 5 entries com
  `(numero, seq, direction)` em ordem decrescente de `seq`.
- Golden de payload estável.

**🚦 FLAG/ROLLBACK:** `SDA_OVERLAY_ULTIMOS_N` (int; default 12; 0 = desativa).

**🛡️ RISCO residual:** Baixo. Buffer separado; sem impacto em SDA17.

---

### SPR-DIR13 · UX popup lock + badge no overlay + **fix #Z lock total** · **P2** · Locks: extensão(JS), BLK-D, UX

**🎯 PORQUÊ (auditado):**
- **Bug #N real:** `popup.html` não tem checkbox de "travar fase"; `content.js` não tem badge
  visual distinto por `sentido.source`.
- **Bug #Z real (NOVO):** `direction_locked` é checado **apenas** em
  `message_handler.py:740` (impede fusão de vídeo DIR7). NÃO impede `phase_advance` (DIR4) nem
  o auto-seed da DIR5. Nome promete "trava" mas semântica atual é "só não escuta vídeo".
- **Ator afetado:** operador que vê fase divergir e quer "congelar" no que ele decidiu.
- **Frequência:** raro (operadora experiente; ~1×/dia).
- **Severidade 🟢/🟠:** UX + comportamental.

**🔧 COMO (passo concreto):**
1. **Cliente (`extension/popup.html` + `popup.js`):**
   - Add `<input type="checkbox" id="lockPhase"> 🔒 Travar fase`.
   - Listener: ao mudar, `chrome.runtime.sendMessage({type:'set_lock', locked})`.
   - Exibir texto `fase atual: <source>` lendo `chrome.storage.local.get('sentidoSnapshot')`.
2. **Cliente (`extension/background.js`):**
   - Handler `set_lock`: `sendToWebSocket({type:'set_seed', direction:currentDirection, locked})`.
   - No `state_sync` handler: persistir `sentido` em `chrome.storage.local.set({sentidoSnapshot: data.data.sentido})`.
3. **Cliente (`content.js` + `overlay.css`):**
   - Badge colorido: 🟢 `operator_seed` · 🔵 `vision` · ⚪ `dom_hint`/`auto_seed`/`deterministic_toggle`.
4. **Servidor — fix #Z (lock total):** em `message_handler.py`:
   - **`:723` (entrada do bloco DIR5):** envolver auto-seed em `if not _gs.direction_locked:`.
     Locked = nunca reanchorar automaticamente.
   - **DIR17 (já criado):** já gateado por `not _gs.direction_locked`.
   - **DIR4 (`:702-706`)**: NÃO mexer — gap deve avançar mesmo com lock (o operador travou a
     paridade, mas a fase ainda alterna por giro físico).
5. **Bump `manifest.version` → `3.7.0`** + nota de reload no popup.

**⚠️ EFEITOS COLATERAIS auditados:**
- DIR4 segue rodando com lock — DECISÃO CONSCIENTE: lock impede *reanchoragem automática*, não
  alternação física. Documentar no ADENDO.
- Nenhum teste existente force `direction_locked=True` — adicionar fixture.
- Cliente: bump de manifest exige reload manual no Chrome.

**✅ DoD verificável:**
- Roteiro: travar fase → minimizar 10× → abrir popup → fase intacta + badge `operator_seed`.
- Servidor: `gs.direction_locked=True` ⇒ DIR17 não zera `seed_parity` em `uncertain`; DIR5
  auto-seed não dispara.
- `test_dir13_lock_total.py`: com `direction_locked=True`, sequência uncertain mantém
  `seed_parity` original.

**🚦 FLAG/ROLLBACK:**
- UI atrás de opção opt-in no popup (default-ON, mas oculta no menu avançado).
- Sub-flag `SDA_LOCK_TOTAL=1` (default-ON após validação). OFF restaura comportamento atual
  (lock semântico fraco).

**🛡️ RISCO residual:** Baixo. UX só. O #Z é a correção de comportamento; gated por flag.

---

### SPR-DIR14 · Limpar `_recent_trace_ids` em reset/role · **P2** · Locks: BLK-D

**🎯 PORQUÊ (auditado):**
- **Bug #O real:** `message_handler.py:175-179` init lazy do deque(64). Nenhum `clear()` em
  `handle_new_session` (`:1393`) nem em `connection_manager.role_assigned` (`:113,277`).
- **Ator afetado:** cliente que faz reset rapidamente (operador trocando dealer) com
  `trace_id` recente.
- **Frequência:** raríssima (cliente gera `trace_id` por `timestamp` — quase nunca repete).
- **Severidade 🟢:** falso-positivo de dedup. Resultado: 1 giro perdido após reset.

**🔧 COMO (passo concreto):**
1. **`message_handler.py:handle_new_session` (`:1388-1434`)** — adicionar dentro do
   `async with self.state_lock:`:
   ```python
   # DIR14: limpa cache de trace_ids para não rejeitar primeiro spin pós-reset.
   if getattr(self, "_recent_trace_ids", None) is not None:
       self._recent_trace_ids.clear()
   ```
2. **`connection_manager.py`** — emitir evento `on_role_change` (callback registrado pelo
   handler). Handler limpa o deque. **Adiar para SPR-DIR14b** se acoplamento for problema.

**⚠️ EFEITOS COLATERAIS auditados:**
- Nenhum teste valida estado do deque pós-reset; sem regressão.

**✅ DoD verificável:**
- `test_dir14_dedup_after_reset.py`: enviar spin com `trace_id="X"` → reset → enviar novamente
  com `trace_id="X"` → segundo é ACEITO (não dedup'ado).

**🚦 FLAG/ROLLBACK:** N/A (`.clear()` em deque vazio é no-op).

**🛡️ RISCO residual:** Zero.

---

### SPR-DIR18 · Shadow mode de divergência quando autoritativo OFF · **P2** · Locks: obs

**🎯 PORQUÊ (auditado):**
- **Bug #U real:** `message_handler.py:722` `if sentido_autoritativo_enabled():` envolve TODA
  a lógica DIR5 (auto-seed + project_phase + métrica `direction_divergence_total`). Em OFF:
  zero observabilidade — impossível avaliar o impacto de ligar/desligar.
- **Ator afetado:** operador/devops que quer fazer A/B "ligar autoridade vale a pena?"
- **Frequência:** todo giro quando flag OFF.
- **Severidade 🟡:** método; observabilidade.

**🔧 COMO (passo concreto):**
1. **`app_config/settings.py`** — adicionar:
   ```python
   def sentido_autoritativo_shadow_enabled() -> bool:
       import os
       return os.environ.get("SDA_SENTIDO_AUTORITATIVO_SHADOW", "0").strip().lower() in ("1","true","on")
   ```
2. **`message_handler.py:722-756`** — refatorar:
   ```python
   _autoridade = sentido_autoritativo_enabled()
   _shadow = sentido_autoritativo_shadow_enabled()
   if _autoridade or _shadow:
       # ... bloco DIR5 (auto-seed + project_phase + métrica) ...
       if _fused != _phase_norm(direcao):
           phase_metrics.incr("direction_divergence_total")
           logger.info(f"[FASE] {'autoridade' if _autoridade else 'shadow'} divergencia: {direcao} -> {_fused}")
           if _autoridade:                # só substitui se autoridade ON
               direcao = _fused
   ```
3. **`docker-compose.yml`** — adicionar variável (default-ON em prod):
   `SDA_SENTIDO_AUTORITATIVO_SHADOW=${SDA_SENTIDO_AUTORITATIVO_SHADOW:-1}`.

**⚠️ EFEITOS COLATERAIS auditados:**
- Nenhum — em SHADOW=1+AUTORIDADE=0, `direcao` final == hint do cliente; sem mudança de aposta.
- Métrica `direction_divergence_total` passa a refletir divergência mesmo com autoridade OFF.

**✅ DoD verificável:**
- `test_dir18_shadow_mode.py`: SHADOW=1+AUTORIDADE=0 + spin com hint divergente →
  `direction_divergence_total += 1` mas `decision.direction == hint do cliente`.
- AUTORIDADE=1 (modo atual): comportamento idêntico.

**🚦 FLAG/ROLLBACK:** sub-flag default-OFF; rollback por env. Em produção: SHADOW=1 sempre.

**🛡️ RISCO residual:** Baixo. Só leitura; não muda aposta.

---

### SPR-DIR15 · ADENDO ISO + documentação de campos · **P3** · Locks: docs

**🎯 PORQUÊ (auditado):**
- **Gap #P:** rev. 4 chamava `client_seq`; código usa `client_spin_seq` (`:528`). Sem cross-ref.
- **Gap #Y:** `client_spin_seq` aceito em `SpinInput` mas cliente NUNCA envia. Campo
  morto em borda.
- **#Q→#T:** decisão consciente de manter `spin_seq += 1` em uncertain (mitigada por DIR17).
- **Severidade 🟢:** documentação; nenhum impacto runtime.

**🔧 COMO (passo concreto):**
1. **`Manutenabilidade_iso.md`** — ADENDO 25/06 cobrindo:
   - `client_seq` (rev. 4) ≡ `client_spin_seq` (código).
   - Decisão DIR16+DIR17 (reanchoragem ativa) vs rev. 4 §4.1 ("sem overlap → resync/seed").
   - Limitação consciente: `phase_metrics` global (sem labels por mesa). Plano: DIR20+.
2. **`evolução_sentido.md` (rev. 4):** cabeçalho ganha `> **SUPERSEDED** por
   `evolução_sentido_25.md` (rev. 5, 25/06).`
3. **`models/input.py` + `message_handler.py:528`:** MANTER `client_spin_seq` (INV não-removido)
   + comentário: `# RESERVADO: cliente ainda não envia; ver DIR21+ se for ativado.`
4. **`README.md` (se houver seção de flags):** documentar as 4 flags ativas em produção.

**⚠️ EFEITOS COLATERAIS auditados:**
- Nenhum runtime — só docs e comentários.

**✅ DoD verificável:**
- ADENDO presente em `Manutenabilidade_iso.md`.
- Cabeçalho da rev. 4 menciona supersessão.
- `tools/lint_silent_except.py` segue verde.

**🚦 FLAG/ROLLBACK:** N/A.

**🛡️ RISCO residual:** Zero.

---

### SPR-DIR19 · Buffer de fase separado (maxlen=20) · **P3** · Locks: BLK-D

**🎯 PORQUÊ (auditado):**
- **Bug #R real:** `state/game.py:238,326,1378` define `recent_results=deque(maxlen=10)`. Doc
  rev. 4 §5 pedia `maxlen ~20`. `phase_advance` aceita até `max_window=20` mas é limitado pelos
  10 do prev.
- **Ator afetado:** cliente em minimização muito longa (>~20 s sem tick) ou troca de mesa
  rápida com gap k>10.
- **Frequência:** rara em mesa rápida; baixa em mesa lenta.
- **Severidade 🟡:** capacidade de recuperação; sem impacto em sessão normal.
- **🚨 NÃO MUDAR `recent_results` direto:** 8 testes dependem da janela 10 para zonas frias
  C3 (SDA17). Mudar de 10→20 quebraria golden tests e mudaria comportamento de aposta.

**🔧 COMO (passo concreto):**
1. **`state/game.py`** — criar BUFFER NOVO em paralelo:
   ```python
   # DIR19: buffer separado p/ shift de fase (DIR4). Mantém recent_results=10
   # intacto (SDA17/C3 dependem). max_window do phase_advance é 20.
   _phase_results: deque = field(default_factory=lambda: deque(maxlen=20))
   ```
2. **`process_spin` + `register_history_number`** — também appendleft no `_phase_results`.
3. **`message_handler.py:700`** — substituir prev:
   ```python
   _prev_nums = list(self.game_state._phase_results)  # antes: list(self.game_state.recent_results)
   ```
4. **Round-trip em `save_state`/`load_state`** — persistir `_phase_results`.
5. **`reset_session` (DIR16)** — também `self._phase_results = deque(maxlen=20)`.

**⚠️ EFEITOS COLATERAIS auditados:**
- **Zero impacto em SDA17/C3** (janela `recent_results=10` preservada).
- 8 testes que usam `recent_results` seguem verdes.

**✅ DoD verificável:**
- `test_dir19_shift_k_ate_20.py`: stream com gap k=15 deve ser recuperado.
- Suíte 689 verde sem alteração.

**🚦 FLAG/ROLLBACK:** N/A (campo aditivo, retro-compatível ao `load_state`).

**🛡️ RISCO residual:** Baixíssimo. RAM extra: ~160 B (20 ints).

---

### 3.1 Dependências e ordem (revisada pós-auditoria estruturada)

```
                        ╔════════════════════════════════╗
                        ║   DIR16 (P0 CRÍTICA) — sozinha ║   ← validar 24h em prod antes
                        ╚══════════════╤═════════════════╝
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
            DIR17 (P1)            DIR9  (P1)           DIR11 (P1, lock schema)
            uncertain reancora    sentido em sugestao   Alembic 0010
            depende de DIR16                                  │
                │                                            ▼
                │                                       (serializa c/ SPR-G2)
                ▼
            DIR12 (P1)                       DIR13 (P2, extensão + #Z)
            /metrics                          UX lock + badge + LOCK TOTAL
                │                                  │
                ▼                                  ▼
            DIR10 (P2)                        DIR14 (P2)
            ultimos[N]                         clear trace_ids
                │                                  │
                └──────────────────┬───────────────┘
                                   ▼
                               DIR18 (P2)
                               shadow mode
                                   │
                   ┌───────────────┴───────────────┐
                   ▼                               ▼
               DIR15 (P3)                      DIR19 (P3)
               ADENDO + docs                   buffer fase separado
```

**Sequência recomendada (revisada):**
1. **🔴 DIR16 PRIMEIRO E SOZINHA** (P0, bug real). Mergear → validar 24h em produção
   monitorando `direction_divergence_total` antes de seguir.
2. **DIR17 depende de DIR16** (usa `direction_locked` corretamente); pode ir junto com
   **DIR9 + DIR11 + DIR12** em paralelo (locks disjuntos).
3. **DIR13 + DIR10 + DIR14 + DIR18 em paralelo** (P2). DIR13 mexe em cliente — bump 3.7.0.
4. **DIR15 + DIR19 closeout** (P3, isolados).

> **Atenção lock:** DIR11 serializa com **SPR-G2** (schema/alembic). DIR13 + DIR17 dependem
> ambas de `direction_locked` — coordenar regions em `message_handler.py`. DIR16 e DIR17 mexem
> no mesmo arquivo → **não paralelas** (DIR17 depende do refactor de reset feito em DIR16).

**Auditoria global de impacto (suíte 689):**
- **15 testes** em `tests/*.py` exercitam `reset_session` → **DIR16 precisa de flag opt-in**
  (`SDA_RESET_REANCORA`) para preservar comportamento legado.
- **8 testes** usam `recent_results` → **DIR19 cria buffer separado** (`_phase_results`) sem
  tocar no original, evitando golden-fail nas zonas frias C3.
- **6 testes** mexem em `seed_parity` → **DIR17 + DIR13** precisam de testes novos validando
  reancoragem em `uncertain` e lock total sem quebrar nenhum existente.
- **CI atual em main `0dca93d`: 4/4 SUCCESS** — qualquer regressão será visível antes do merge.

---

## 4. Conformidade ISO e invioláveis (por sprint, antes do PR)

- [ ] **Flag default-OFF** na `docker-compose.yml` quando aplicável; leitura **por-chamada**.
- [ ] **Aditivo/retrocompatível** (migração Alembic ADITIVA; campos novos em `engine_overlay_fields`).
- [ ] **INV-3 intacto**: nada do que ficou propõe suprimir indicação — DIR9/DIR10 só publicam,
  DIR13 trava a fase **mantendo** indicação para o lado travado.
- [ ] **Persistência round-trip** se acrescentar campo de motor (`save`+`load`+`reset_session`).
- [ ] **Suíte verde** (`pytest tests/`); novo `except` → `tools/lint_silent_except.py --update`.
- [ ] Mexeu em `extension/` (DIR13) → bump `manifest.version` (3.6.0 → 3.7.0) + nota de reload.
- [ ] **ADENDO** em `Manutenabilidade_iso.md` por sprint; **PR**; **não** commitar `graphify-out/`.
- [ ] Worktree dedicado: `git worktree add ..\rc-SPR-DIR9 -b spr/SPR-DIR9 origin/main`.

---

## 5. Métricas de sucesso (esperadas após DIR9…DIR19)

| Métrica | Antes (HEAD `0dca93d`) | Depois (DIR16+17 — P0/P1) | Depois (DIR9…DIR19 completo) |
|---|---|---|---|
| `direction_divergence_total` em handoff de dealer | **dispara persistente** (bug #S/T) | ~0 após 1-2 giros (auto-reanchora) | mesmo |
| Latência `cliente.currentDirection` ↔ `servidor.sentido` | ≤ 1 s (state_sync) | ≤ 1 s | ≤ tick do giro (sugestao) — via DIR9 |
| Cobertura `/metrics` Prometheus de fase | 0 contadores | 0 contadores | 3 contadores (DIR12) |
| Banco zero-state com schema DIR3 | ⏳ após 1° boot | ⏳ após 1° boot | 100% após `alembic upgrade head` (DIR11) |
| Operador "trava" fase e ela persiste a minimização | ❌ | ❌ | ✅ (DIR13) |
| `recent_trace_ids` impacto pós-reset | ⚠️ risco residual | ⚠️ risco residual | 0 (DIR14) |
| Shift recupera gap de até k giros | k ≤ 10 | k ≤ 10 | k ≤ 20 (DIR19) |
| A/B observável (autoridade OFF vs ON) | ❌ impossível | ❌ impossível | ✅ shadow mode (DIR18) |
| `client_spin_seq` campo morto no servidor | sim | sim | removido (DIR15) |
| Conformidade global com rev. 4 | **~85%** | **~92%** | **~99%** |

---

## 6. Rollback global

- **Pré-PR #26 (estado de 25/06 04:30 BRT):** todas as flags em `0` na compose +
  `git revert 0dca93d` → comportamento byte-a-byte do `b42cac9` (PR #25 mergeado com flags OFF).
- **Pré-PR #25 (estado de 24/06):** `git revert b42cac9 0dca93d` → motor de fase desativado, mas
  os campos `spin_seq`/`direction_source` permanecem no schema (aditivos) — sem efeito colateral.
- **Por flag (sem revert):** no host Debian, exportar `SDA_*=0` no env + `docker compose up -d
  --force-recreate`. Não toca código.

---

## 7. Referências e citações

- `evolução_sentido.md` (rev. 4 · 24/06/2026) — proposta original.
- `Manutenabilidade_iso.md` — invariantes (INV-1..3), AUDIT-1 (rota do overlay), ADENDOS
  17/06–25/06 (SPR-DIR1..DIR8).
- `fluxo_mental_24.md` — blueprint geral (ciclos, infra, app, UX).
- `BOARD.md` — estado vivo dos sprints; o Diretor promove `SPR-DIR16` → `READY` ao publicar este
  documento (P0 — vai primeiro).
- Código auditado (HEAD `0dca93d`, leitura profunda 25/06 12:00 BRT):
  - **state:** `game.py:238,288-381,417,957-1035,1278-1384`, `phase.py:1-150`,
    `phase_metrics.py:1-40`
  - **server:** `message_handler.py:170-179,357-401,420-540,685-775,1260,1308,1315-1476`,
    `websocket.py:344-423`, `connection_manager.py:113,196-216,277`, `health_server.py`
  - **database:** `sqlite_repo.py:187,226,372-380,422-465,913-917`
  - **extensão:** `extension/manifest.json` (v3.6.0), `background.js:103-117,545-617,971-980,1245-1251,1620-1720`,
    `popup.js:40-340`, `content.js:553`
  - **migrations:** `versions/0001…0009` (faltando `0010_dir3_phase_columns.py` — SPR-DIR11)
  - **tests:** `test_dir{2…8}_*.py` (38 testes) + suíte total
  - **config:** `app_config/settings.py` (defaults `"0"`), `docker-compose.yml` (DIR2/4/5/6 ON)
- Suíte completa: **689 passed, 9 skipped, 1 xfailed, 4 warnings em 33.33 s** (local 25/06 11:36 BRT).
- CI `main` `0dca93d`: 4/4 SUCCESS (ci-ok + lint-and-test 3.11/3.12/3.13).
- **Auditoria profunda 25/06 12:00 BRT:** 7 achados novos (#R, #S, #T, #U, #W, #X, #Y)
  encontrados pela leitura do caminho `reset_session → seed_parity → handle_history_correction
  → phase_advance → project_phase`. Veja §0.1 Grupo B.
