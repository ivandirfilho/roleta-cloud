# Evolução do Sentido — Sincronismo de Fase (Proposta · rev. 4 · auditada e verificada)

> **Tema:** tratar o **sentido do giro** como **fase alternada** (a roleta gira um sentido por vez) e
> tornar o **sincronismo dessa fase** robusto à minimização do Chrome, à troca de master e à perda de
> giros — **reusando canais e dados que já existem** no sistema. Deixa pronta a entrada do **vídeo**.
> **Tipo:** proposta (visão + sprints). Não altera código — orienta os executores.
> **Base:** código em `HEAD 13a2b71` (24/06/2026). **Toda afirmação foi reverificada no código** (§0.2).
> **rev. 4 (24/06):** verificação cética das afirmações da rev. 3; correção de 2 imprecisões
> (`process_spin`≠`add_spin`; SW vs popup) e 1 reforço (o canal autoritativo **já existe**:
> `state_sync` 1 s carrega `target_direction`). Sprints finais prontas para execução.

---

## 0. TL;DR (sumário executivo)

**O sentido não é lido da roleta — é uma fase alternada** (a roleta gira um sentido por vez). Por isso
o operador informa a fase **uma vez** e o sistema **alterna**: alternar **está correto**, é a física. O
bug não é a alternância — é a **perda de sincronismo de fase** quando giros são **perdidos** (SW
minimizado) ou **duplicados** (re-render), e a fase "anda".

A fase mora hoje na global volátil `currentDirection` do *service worker* (SW) MV3 — que **perde-se ao
minimizar** porque o **SW não a re-hidrata no boot** (só o `popup.js` re-hidrata, mas o popup não é
quem envia ao servidor). E o **avanço da fase é por evento**: o cliente processa só `newNumbers[0]` e
alterna **uma vez**, mesmo quando **k>1** giros entraram entre dois ticks de 2 s. Pior: o cliente **já
envia os 12 últimos números** (`allNumbers`) e o servidor **os ignora**; o servidor **já transmite
`target_direction` a cada 1 s** (`state_sync`) e o cliente **não o consome** para corrigir a paridade.

**A munição e os canais para resolver já existem.** Proposta: tornar o **servidor a autoridade da
fase**, derivada de `fase(n)=seed XOR ((n−seed_n) mod 2)`, com `n` (contador de **giros reais**)
mantido por **reconciliação dos últimos resultados** (shift), e **publicada no `state_sync`/`sugestao`
que já trafegam** (via o ponto de extensão aditivo `engine_overlay_fields()`). A **correção do
operador** vira **reancoragem de fase**, não recálculo cego. O **vídeo** entra como confirmação de
fase. **8 sprints** (SPR-DIR1…DIR8), todas **flag default-OFF**, **aditivas**, **testáveis**.

---

## 0.1 Bugs (consolidado)

| # | Sev. | Bug | Evidência (verificada) | Sprint |
|---|---|---|---|---|
| **#1** | 🔴 | `currentDirection` (global do SW) perde-se ao minimizar; **o SW não a relê no boot** (só `popup.js` relê) | `background.js:103,1690`; boot `:901` sem `get`; `popup.js:101-103` | DIR1 |
| **#G** | 🔴 | **Gap de fase**: cliente processa só `newNumbers[0]` e alterna **1×** mesmo com **k>1** giros novos entre ticks → defasa `(k−1)`. Ocorre **com o SW vivo** | `background.js:1620-1622,1686` | DIR1, DIR4 |
| **#H** | 🟠 | **`allNumbers` ignorado**: cliente envia 12 últimos, **nenhum** consumo no servidor | `background.js:1662`; grep repo: 0 consumo | DIR4 |
| **#A** | 🔴 | **Histórico fabricado**: `historico_inicial`/`correcao` chamam `process_spin` com direção inventada → envenena `timeline_cw/ccw` | `message_handler.py:1209-1214,1240-1245`; `background.js:1700-1714` | DIR2 |
| **#2** | 🟠 | Fase não-autoritativa: servidor **já manda** `target_direction` no `state_sync` (1 s) mas é **derivado do cliente** e o cliente **não o consome** p/ corrigir | `websocket.py:401`; `background.js:545-548` | DIR4, DIR5 |
| **#C** | 🟠 | **Reset de dealer dessincroniza**: `reset_session` zera `last_direction`, cliente **não** reseta `currentDirection` | `message_handler.py:1269`; `game.py:357`; `background.js:550-554` | DIR1, DIR5 |
| **#D** | 🟠 | **Handoff de master** injeta a fase default (`'horario'`) do novo master no estado global | `connection_manager.py:196-216`; `message_handler.py:405-413` | DIR5 |
| **#3** | 🟡 | Sem `spin_seq` (âncora): a fase não é recuperável de um contador | `background.js:1686` | DIR3 |
| **#E** | 🟢 | Defaults silenciosos `get("direcao","horario")` mascaram perda | `message_handler.py:488,1211,1242` | DIR2, DIR3 |

---

## 0.2 Verificação de afirmações (auditoria rev. 4) — o que foi reconferido no código

| Afirmação | Veredito | Prova |
|---|---|---|
| Fluxo normal registra o giro via `process_spin` (a rev.3 dizia `add_spin`) | ✅ **corrigido** | `message_handler.py:662` `game_state.process_spin(numero,direcao)`; def em `game.py:364` |
| `currentDirection` nunca re-hidratado | ⚠️ **refinado** | re-hidratado **só** em `popup.js:101-103`; o **SW** (`background.js`) não — e é o SW que envia |
| Servidor "nunca devolve o sentido" | ⚠️ **corrigido** | `state_sync` (1 s) **já inclui** `target_direction` (`websocket.py:401`); cliente só repassa ao overlay (`background.js:545-548`), não corrige a paridade |
| `allNumbers` é ignorado pelo servidor | ✅ confirmado | grep no repo: único uso real é o envio `background.js:1662`; `core/roulette.py:315 all_numbers` é outra coisa |
| `sessao_resetada` não reseta `currentDirection` | ✅ confirmado | `background.js:550-554` só loga e repassa ao content |
| `save_decision` roda por giro (base do `id`) | ✅ confirmado | `message_handler.py:988`; `decisions.id AUTOINCREMENT` `sqlite_repo.py:187` |
| Existe canal de heartbeat servidor→cliente | ✅ **achado** | `broadcast_heartbeat()` 1 s `websocket.py:344-423`; extensível via `engine_overlay_fields()` `message_handler.py:345`,`websocket.py:418` |
| Servidor notifica o role ao cliente | ✅ **achado** | `role_assigned` `background.js:557-562` (gatilho natural de resync no handoff) |
| `target_direction = oposto(last_direction)` | ✅ confirmado | `game.py:1014-1018` |
| `recent_results` (deque 10, recente em [0]) populado no fluxo | ✅ confirmado | `game.py:238,380` (`appendleft` em `process_spin`) |
| Ordem do DOM = recente primeiro | ⚠️ **premissa** | `extractResultsFromPage` `background.js:1777-1818` faz `numbers.push` sem `reverse`; o código **assume** `[0]`=mais recente (`:1622`). DIR4 deve validar por provider |

> **Honestidade:** os itens ⚠️ eram imprecisões da rev. 3, agora corrigidas. A correção **fortalece** a
> proposta — o canal e o campo de autoridade **já existem**; falta torná-los **independentes** (shift)
> e **consumi-los** no cliente.

---

## 1. Como funciona HOJE (verificado)

### 1.1 Caminho de um giro
```
Escuta Beat (Chrome MV3) — só o MASTER envia dados              Servidor (Python, asyncio)
─────────────────────────────                                  ────────────────────────────
readLoop ~2s: extractResultsFromPage() → numbers[] (DOM)        connection_manager: elege MASTER
  newHash = numbers.slice(0,5).join(',')                         gate role==master? senão NOT_MASTER
  if newHash != lastHash:                                        is_duplicate_spin(numero,dir,ms)
     newNumber = numbers[0]   ← SÓ o topo (perde k>1, #G)        handle_new_result:
     novo_resultado{ numero, DIRECAO, allNumbers[12], … } ────►   • IGNORA allNumbers (#H)
     currentDirection alterna 1× (global volátil, #1)              • process_spin(numero,direcao):
                                                                       recent_results.appendleft(numero)
                                                                       last_number/last_direction = …
                                                                   • SDA17; save_decision (id++)
                              ◄─ sugestao (ultimo_numero) ──────   responde
   ░ a cada 1s ░             ◄─ state_sync { target_direction,…}   broadcast_heartbeat (já manda a dir!)
   (cliente só repassa ao overlay; NÃO corrige currentDirection — #2)
   [reset] content.js → nova_sessao ─────────────────────────►    reset_session(): last_direction=""
                              ◄─ sessao_resetada ──────────────    (cliente NÃO reseta currentDirection #C)
```

### 1.2 Infra que JÁ EXISTE e seria reusada (verificada)

| Recurso | Local | Hoje |
|---|---|---|
| `state_sync` broadcast **1 s** com `target_direction` | `server/websocket.py:344-423` (`:401`) | canal de autoridade **subutilizado** (#2) |
| `engine_overlay_fields()` (campos aditivos p/ `sugestao`+`state_sync`) | `server/message_handler.py:345`; `websocket.py:418` | **ponto de extensão** p/ publicar a fase |
| `role_assigned` (servidor→cliente) | `extension/background.js:557-562` | gatilho de **resync** no handoff |
| `allNumbers[12]` enviado | `extension/background.js:1662` | **ignorado** (#H) — alavanca do shift |
| `recent_results` (deque 10, recente=[0]) | `state/game.py:238,380` | mantido (C3) — não usado p/ sincronismo |
| `decisions.id AUTOINCREMENT` + `result_actual` | `database/sqlite_repo.py:187,226` | sequência física de giros |
| `target_direction = oposto(last)` | `state/game.py:1014-1018` | a fase-alvo já é derivável |

### 1.3 Onde a fase é decidida/avançada hoje (volátil)

| Peça | Local | Papel |
|---|---|---|
| `currentDirection='horario'` (global SW) | `extension/background.js:103` | fase volátil (#1) |
| `newHash` (5 primeiros) detecta "mudou" | `extension/background.js:1424,1620` | não conta **quantos** giros |
| processa só `numbers[0]`, alterna 1× | `extension/background.js:1622,1686` | descarta giros perdidos (#G) |
| `setDirection` recalcula p/ trás | `extension/background.js:1170-1184` | correção cega (vira #A) |
| `process_spin` registra o giro | `state/game.py:364`; chamada em `message_handler.py:662` | atualiza `last_*`/timelines/`recent_results` |

---

## 2. Modelo conceitual — sentido é FASE

`seed_parity` = fase informada pelo operador **1×** (no giro `seed_n`); `n` = índice do **giro real**.
A roleta alterna, então a fase é **determinística**:
```
fase(n) = seed_parity XOR ((n − seed_n) mod 2)
```
Não é preciso "lembrar" a fase numa variável volátil — basta **(seed, n)**. O problema reduz-se a
**manter `n` alinhado com a realidade**, e a realidade chega de graça nos **últimos resultados**.

---

## 3. Diagnóstico — a causa comum

**Uma** causa, vários sintomas: a fase é mantida por **contagem implícita no nó volátil**, sem âncora
nem reconciliação. Daí perde-se no boot do SW (#1) e no handoff de master (#D); sub-conta giros (#G);
dessincroniza no reset (#C); e ao "corrigir" **inventa** direção que **envenena o motor** (#A). A
munição (últimos resultados #H) e o canal de autoridade (`state_sync` #2) **existem e são ignorados**.

> **Cura:** servidor = autoridade; fase **derivada de (seed, n)**; `n` mantido por **shift dos últimos
> resultados**; **publicada no canal que já existe**; correção = **reancoragem**.

---

## 4. Arquitetura-alvo (reusando o que existe)

```
   CLIENTE = SENSOR (só o master envia)            SERVIDOR = AUTORIDADE DA FASE
   ─────────────────────────────────              ───────────────────────────────────────────
   novo_resultado{ numero, allNumbers[12],         Phase Engine (flag SDA_SENTIDO_AUTORITATIVO):
     direction_hint, client_seq?, trace_id } ────►  1) SHIFT vs recent_results → k giros reais
                                                        n += k  (k=0 dup · 1 ok · ≥2 gap · 0-overlap→resync)
                                                     2) fase(n)=seed XOR ((n−seed_n)%2)
                                                     3) histórico batch = NÃO-DIRECIONAL
   consome state_sync.sentido p/ corrigir  ◄──1s──  4) PUBLICA via engine_overlay_fields():
   currentDirection (não inventa)                       state_sync/sugestao += sentido{last_seq,
   resync no reconnect/role_assigned/reset ◄────────       last_dir,next_dir,locked} + ultimos[N]
```
- **Sem mensagem nova:** a fase viaja no `state_sync` (1 s) e na `sugestao` via `engine_overlay_fields()`.
- **Resync** = o próprio `state_sync` (chega em ≤1 s ao reconectar) + gatilho `role_assigned` (handoff)
  + `sessao_resetada` (reset). O cliente **bloqueia etiquetagem** até o 1º `state_sync` pós-evento.

### 4.1 Reconciliação por shift (conta giros reais)
`prev`=`recent_results` (estender p/ ~20); `new`=`allNumbers`.
```
menor k≥0 tal que new[k:k+m] == prev[0:m]   (cauda do novo casa com a cabeça do antigo)
  k=0 dup/re-render (fase não avança) · k=1 normal · k≥2 GAP recuperado · sem overlap → resync/seed
```
Robusto a repetição (subsequência ordenada). Ambíguo → `phase_uncertain` (INV-3: nunca suprime aposta).
**Premissa a validar (DIR4):** `numbers[0]`=mais recente (o código já assume, `background.js:1622`).

### 4.2 Correção = REANCORAGEM (mata #A)
O operador afirma a fase de um giro conhecido; o servidor fixa `(seed_parity, seed_n)` e **deriva** o
resto. Não reescreve timelines com palpite — idempotente e auditável. Substitui o `setDirection`/
`correcao_historico` retroativos.

---

## 5. Modelo de dados (aditivo)

- **`state/game.py`** (round-trip `save`+`load`+`reset_session`): `spin_seq:int` (n; reinicia no
  reset), `seed_parity:str`, `seed_n:int`, `direction_source:str`, `direction_locked:bool`;
  `recent_results` maxlen ~20.
- **SQLite** (`database/sqlite_repo.py`, migração **aditiva**, sem downgrade): colunas nullable em
  `decisions`: `spin_seq INTEGER`, `direction_source TEXT`, `direction_confidence REAL`,
  `direction_next TEXT`, `phase_uncertain BOOLEAN` (backfill como SP-13).
- **Projeção pura** (§2) — testável; histórico batch entra como contexto **não-direcional**.

---

## 6. Sprints finais (executáveis)

> Prefixo **SPR-DIR** (não colide com `SPR-S*` do `BOARD.md`/§7). O Diretor promove via
> `sprints/_BRIEF_TEMPLATE.md`. Toda sprint: **flag default-OFF**, **aditiva**, **suíte verde** (`pytest tests/`), **PR**.

### SPR-DIR1 · Cliente: sobreviver, consumir o que já chega e contar giros · P0 · Lock: extensão(JS)
- **Bugs:** #1, #G(parcial), #C(parcial), #2(consumo).
- **Por quê — infra:** segue a doc do Chrome (ler do storage no wake), risco mínimo, só cliente.
  **app:** o `state_sync` **já traz `target_direction`** a cada 1 s (`websocket.py:401`) — basta
  **consumi-lo** no `background.js` p/ corrigir `currentDirection` ao acordar/reconectar; e avançar a
  fase pelo **nº de números novos** (diff `numbers` vs `lastHash`), não +1. **UX:** sintoma some sem ação.
- **Como:** (1) no boot do SW (`background.js:~901`) re-hidratar `currentDirection`+`seed` do storage;
  (2) no handler `state_sync` (`:545-548`) passar a **atualizar `currentDirection`** a partir de
  `data.target_direction`; (3) no `sessao_resetada` (`:550`) resetar p/ o seed; (4) ao detectar mudança,
  alternar a fase pelo nº de entradas novas. Bump `manifest.version` + reload.
- **DoD:** roteiro minimizar/restaurar 10× + 2 giros num tick + reset 3× sem defasagem; log com k.
- **Flag/rollback:** `directionPhasePolicy` (default ON é seguro: só consome estado já enviado); `git revert`+reload.

### SPR-DIR2 · Histórico NÃO-DIRECIONAL + correção = reancoragem · P0 · Locks: BLK-G
- **Bugs:** #A, #E(batch).
- **Por quê — app:** é o bug que **muda a aposta** (timelines envenenadas por direção inventada).
  **infra:** corrige na borda de ingestão, sem refatorar SDA17. **UX:** acaba "aposta estranha" ao abrir a mesa.
- **Como:** em `handle_initial_history`/`handle_history_correction` (`message_handler.py:1203-1257`),
  **não** alimentar timelines com direção fabricada (tratar números como contexto não-direcional);
  `correcao_historico` vira **reancoragem** (§4.2). No cliente, parar de inventar alternância retroativa
  (`background.js:1700-1714`). Flag `SDA_HISTORICO_NAO_DIRECIONAL`.
- **DoD:** teste prova `timeline_cw/ccw` **imutável** sob histórico sem direção real; golden test SDA17.
- **Flag/rollback:** `SDA_HISTORICO_NAO_DIRECIONAL=0` restaura o atual.

### SPR-DIR3 · Fundação: `spin_seq` (giros reais) + fase determinística · P1 · Locks: schema, alembic, BLK-G
- **Bugs:** #3 (fundação p/ #2/#D).
- **Por quê — infra:** Event Sourcing: `spin_seq` torna a fase **projeção auditável** de `(seed,n)`.
  Flag **OFF** = só observar (gravar + medir divergência). **app:** base p/ shift/resync.
- **Como:** migração **aditiva** (§5); `game_state` ganha os campos com round-trip; `SpinInput` ganha
  `direction_source`/`client_seq` opcionais (`models/input.py`). `SDA_SENTIDO_AUTORITATIVO=0`: ainda
  obedece o master, registra divergência cliente↔projeção.
- **DoD:** `alembic upgrade head`; `pytest` da projeção pura; round-trip testado.
- **Flag/rollback:** `SDA_SENTIDO_AUTORITATIVO=0` + migração aditiva.

### SPR-DIR4 · Reconciliação por shift (consumir `allNumbers`) · P1 · Locks: BLK-D, BLK-G — **CENTRAL**
- **Bugs:** #G, #H, #1(cura server-side), #2(independência).
- **Por quê — app:** usar `allNumbers` (ignorado) + `recent_results` p/ **contar giros reais** e avançar
  a fase em **k**; aqui a fase deixa de ser circular (derivada do cliente) e vira **independente**.
  **infra:** reusa estruturas; `k=0` é dedup melhor que numero+dir+ms. **UX:** após minimizar horas, a fase **se corrige sozinha**.
- **Como:** consumir `allNumbers` em `handle_new_result`; estender `recent_results` (~20); shift (§4.1);
  `n += k`; `phase_uncertain` se ambíguo; **validar a ordem do DOM por provider** antes de confiar.
  Flag `SDA_PHASE_RECONCILE`.
- **DoD:** streams (dup, gap k≥2, troca de mesa) recuperam a fase; métrica `gap_recuperado_total`.
- **Flag/rollback:** `SDA_PHASE_RECONCILE=0` volta ao avanço +1.

### SPR-DIR5 · Publicar a fase autoritativa no canal existente + resync · P1 · Locks: BLK-D
- **Bugs:** #2, #C, #D.
- **Por quê — infra:** **sem mensagem nova** — adicionar `sentido{last_seq,last_dir,next_dir,locked}` +
  `ultimos[N]{numero,seq,direction}` ao `engine_overlay_fields()` (`message_handler.py:345`), que já
  alimenta `state_sync`(1 s) e `sugestao`. **app:** cliente **sobrescreve** `currentDirection` e a fila
  local; resync via `state_sync`+`role_assigned`+`sessao_resetada`. **UX:** overlay com setas corretas do servidor.
- **Como:** servidor preenche o bloco a partir da projeção (DIR4); cliente bloqueia etiquetagem até o 1º
  `state_sync` pós-evento. Com `SDA_SENTIDO_AUTORITATIVO=1` o servidor é autoridade; `direction_hint` é palpite.
- **DoD:** integração: master dorme/cai/troca → fase idêntica à do servidor; `direction_divergence_total → 0`.
- **Flag/rollback:** flag OFF volta ao modo "obedece master"; campos aditivos ficam inócuos.

### SPR-DIR6 · Idempotência por `spin_seq` + gap → auto-resync · P1 · Locks: BLK-D
- **Bugs:** #3 (endurecimento), consolida DIR4.
- **Por quê — infra:** dedup por `trace_id`+`spin_seq` (Azure: "skip duplicates") supera numero+dir+ms
  (`message_handler.py:146-168`). **app:** buraco de sequência → auto-resync. **UX:** zero aposta fantasma.
- **Como:** estender `is_duplicate_spin` p/ sequência; gap → resync; sub-flag OFF.
- **DoD:** streams adversariais mantêm a fase.
- **Flag/rollback:** sub-flag default-OFF.

### SPR-DIR7 · Fusão de fontes: vídeo confirma a fase · P2 · Locks: BLK-D
- **Por quê — app:** espelha `vision_source`/`vision_confidence` do número (`input.py:39-41`); o vídeo
  publica confirmação de fase com confiança, fundida por prioridade (`operator>vision>toggle`) e pode
  **resolver `phase_uncertain`**. **infra:** contrato pronto com vídeo OFF; cliente não muda.
- **Como:** generalizar o Phase Engine p/ N fontes; ingestão `direction_event` (flag própria); thresholds.
- **DoD:** fonte `vision` de alta confiança resolve ambiguidade; sem vídeo, idêntico.
- **Flag/rollback:** `SDA_DIRECTION_VISION=0`.

### SPR-DIR8 · UX "seed 1×" + observabilidade da fase · P2 · Locks: BLK-L (harness), obs
- **Por quê — UX:** operador define a fase **1×** e pode **travar**; overlay mostra **fase+origem+setas**
  autoritativas. **infra/app:** métricas reusam o pipeline `master_present` (`health_server.py:133`):
  `direction_divergence_total`, `gap_recuperado_total`, `phase_uncertain_total`.
- **Como:** popup seed único + "travar"; badge no overlay (`content.js`); 3 métricas; painel.
- **DoD:** painel mostra divergência → ~0 após DIR5; seed persiste à minimização e ao reset.
- **Flag/rollback:** UI atrás de flag; métricas aditivas.

### 6.1 Dependências e ordem de execução
```
DIR1 ─ (cliente)         ┐ locks disjuntos → PARALELOS, primeiro (maior valor imediato)
DIR2 ─ (server/BLK-G)    ┘
DIR3 ─► DIR4 ─► DIR5 ─► DIR6
          DIR3 ─► DIR7
                  DIR5 ─► DIR8
```
**Sequência recomendada:** (1) DIR1 **e** DIR2 em paralelo → alívio imediato + motor limpo; (2) DIR3
(schema, serializa com outras de schema); (3) DIR4 (cura estrutural); (4) DIR5; (5) DIR6; (6) DIR7/DIR8.

---

## 7. Conformidade ISO & invioláveis (por sprint)
- [ ] **Flag default-OFF** na `docker-compose.yml`; leitura **por-chamada** (não cachear).
- [ ] **Aditivo/retrocompatível** (migração + campos em `engine_overlay_fields`; nada removido/renomeado).
- [ ] **INV-3 intacto**: a fase decide **para qual lado** apostar — `phase_uncertain` **nunca** suprime a indicação.
- [ ] **Persistência round-trip** de campo novo de motor (`save`+`load`+`reset_session`).
- [ ] **Suíte verde** (`pytest tests/`); novo `except` → `tools/lint_silent_except.py --update`.
- [ ] Mexeu em `extension/` → bump `manifest.version` + nota de reload.
- [ ] **ADENDO** em `Manutenabilidade_iso.md` por sprint; **PR** (sem tocar `main`); **não** commitar `graphify-out/`.

## 8. Riscos, métricas e rollback global
- **Risco:** shift mal-resolvido por repetição rara. **Mitig.:** subsequência ordenada + `phase_uncertain`
  + (DIR7) confirmação por vídeo; INV-3 nunca deixa sem aposta.
- **Risco:** ordem do DOM diferir por provider. **Mitig.:** DIR4 valida a ordem antes de confiar (premissa §0.2).
- **Risco:** histórico não-direcional reduzir aquecimento do SDA17. **Mitig.:** DIR2 atrás de flag + golden test.
- **Risco:** transição OFF↔ON. **Mitig.:** DIR3 só observa; autoridade só em DIR5; rollback por flag.
- **Métricas:** `direction_divergence_total → ~0`; **zero** "duplo mesmo sentido" pós-minimização/gap em 1 h;
  `gap_recuperado_total`>0 com minimização; timelines SDA17 **imutáveis** sob histórico sem direção; `spin_seq` contíguo.
- **Rollback global:** todas as flags em `0` restauram o comportamento atual byte-a-byte (tudo é só-adição).

## 9. Referências
- Chrome — *Service worker lifecycle* (globais se perdem; relê do storage no wake).
- Azure Architecture Center — *Event Sourcing* (idempotência por sequência).
- microservices.io — *Pattern: Event sourcing*.
- *Offline-first / state reconciliation* (réplica do cliente reconcilia por diff ao reconectar).
- *Server-authoritative + client-side prediction/reconciliation* (jogos em tempo real).
- Código auditado (citações §0.1/§0.2/§1): `extension/background.js`, `extension/popup.js`,
  `extension/content.js`, `models/input.py`, `state/game.py`, `server/message_handler.py`,
  `server/websocket.py`, `server/connection_manager.py`, `database/sqlite_repo.py`.
