# SPR-V2 · Blindagem MV3 da extensão: um escritor, baseline íntegro e perda observável · Bloco BLK-D/extensão · Pri P0

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §3 (furos C/C2), §4.2, §7, §10.5, §11.4-B · `Manutenabilidade_iso.md`.

## Meta
```text
blocked_by: []                      # código independente de SPR-V1 (locks disjuntos: servidor × extensão)
locks:      [extensão-JS, popup, manifest]
touches:    [extension/background.js, extension/popup.js, extension/popup.html,
             extension/manifest.json, extension/phase_align.js (novo), tests/js/ (novo)]
base_sha:   origin/main
branch:     spr/SPR-V2
```
**Rollout ≠ código:** este PR pode ser feito em paralelo com SPR-V1, mas a **instalação** no Chrome do
operador acontece **depois** do deploy do SPR-V1 (ver "Ordem de ativação"). SPR-V3, SPR-V5 e SPR-V6A
dependem deste sprint e tocam os mesmos arquivos: não abra nenhum deles antes deste PR mergear.
**Ponto comum com SPR-V1:** apenas o **ADENDO em `Manutenabilidade_iso.md`** — escreva **em append no
fim do arquivo**, nunca edite adendos existentes, para que o rebase seja trivial.
**Dependência de campo (não de código):** o Bloco 4.4 consome `state_sync.phase_authority`, entregue
pelo **SPR-V1 Bloco 4.5**. Implemente tolerante à ausência: sem o campo, a reconciliação fica
desarmada e o sprint continua entregável e testável isoladamente.

## Setup (worktree próprio — NÃO use o working dir do Diretor)
```text
git -C "C:\Users\Windows\Desktop\Roleta Cloud" worktree add ..\rc-SPR-V2 spr/SPR-V2
cd ..\rc-SPR-V2
git rev-parse --show-toplevel   # confirme que você NÃO está no worktree do Diretor
```
(Se o branch não existir no remoto: `git worktree add ..\rc-SPR-V2 -b spr/SPR-V2 origin/main`.)

## Objetivo (1 frase)
Impedir que a extensão **fabrique giros e inverta a fase** a partir de leituras parciais, reentrantes
ou de frame errado — e tornar **observável** toda leitura descartada, para que o fix não troque
"giro fantasma" por "parada silenciosa".

## Contexto mínimo (por que existe)
O service worker MV3 lê o DOM da mesa a cada ~2s e envia `novo_resultado` com uma direção que ele
**alterna localmente** (a direção não é lida, é inferida). Com a janela minimizada o Chrome pausa rAF
e faz throttling dos timers da página: o DOM fica em estados intermediários. Consequências medidas em
produção: giro fantasma reenviado 2s depois **com a direção oposta**, e rajadas de `phase_uncertain`
no servidor. Três causas no cliente:
- **Baseline curto**: o hash de mudança usa só **5** dos números (`background.js:1508`), mas o payload
  manda **12** (`:1756`) — o alinhamento do servidor compara 12 contra um baseline validado em 5.
- **"1 conservador"**: `countNewSpins` (`:117-131`) começa em `k=1` (não existe o caso `k=0` de
  re-render idêntico) e retorna `1` quando **nada** alinha — "não alinhou" significa *leitura
  suspeita*, não *1 giro novo*. Cada flap = 1 giro fantasma + 1 flip espúrio.
- **Reentrância**: `onAlarm` chama `readResults()` **sem `await`** (`:1063`); com frame throttled o
  `executeScript` pode passar de 2s → duas execuções concorrentes leem o mesmo `lastHash`, ambas
  "detectam" o giro e enviam **2×, com 2 flips**.
Some-se a corrida de boot: o alarme pode disparar antes da re-hidratação de `currentDirection`
(`:974-980`), e o primeiro envio pós-acordar sai com a fase literal `'horario'`.

## Âncoras (onde entrar — NÃO faça grep cego)
- `extension/manifest.json:4` — `"version": "3.9.1"` (**a proposta cita 3.8.0; está desatualizada** —
  bump para **3.10.0**). `:28-34` — content script com `all_frames: true` (padrão a imitar em V5).
- `extension/background.js:74` — `lastHash` no state; `:103-109` — globals `currentDirection` /
  `directionSeed` (**morrem quando o SW dorme**).
- `extension/background.js:112` — `phaseFlip`; `:117-131` — **`countNewSpins`** (loop de `k=1`,
  `return 1` conservador em `:130`).
- `extension/background.js:391` e `:1127` — outras escritas de `state.lastHash` com `slice(0,5)`.
- `extension/background.js:576-611` — handler de `state_sync` (lê/escreve `currentDirection`, `:595`,
  `:611`).
- `extension/background.js:974-980` — re-hidratação por callback (**corrida de boot**).
- `extension/background.js:1059-1067` — `onAlarm` → `readResults()` **sem await**.
- `extension/background.js:1241-1255` — `setDirection` (toggle manual do popup; persiste
  `directionSeed`/`currentDirection`).
- `extension/background.js:1300-1330` — `getState()` / `saveState()` (**read-modify-write sem
  serialização** — é aqui que nasce o "último a escrever ganha").
- `extension/background.js:1457-1500` — `readResults()` e a **seleção de frame** (`:1492-1500` pega o
  **primeiro** frame com números e dá `break`).
- `extension/background.js:1508` — `newHash = newNumbers.slice(0, 5).join(',')` ← **hash de 5**.
- `extension/background.js:1704-1720` — comparação de hash e atualização de baseline.
- `extension/background.js:1710-1712` — `countNewSpins(newNumbers, _prevResults)` e o cálculo de
  `sendDir`; `:1756` — `allNumbers: newNumbers.slice(0, 12)`; `:1782` — flip de `currentDirection`.
- `extension/popup.js` / `popup.html` — hoje exibem apenas elements/numbers/error.
- Espelho conceitual no servidor: `state/phase.py:47-77` (`reconcile_shift`) — o algoritmo do cliente
  precisa ter **a mesma disciplina de evidência**.

## Tarefa (blocos — um commit por bloco; PR único)

### Bloco 1 — módulo puro e testável (`extension/phase_align.js`, UMD)
1. Extrair para um módulo **sem dependência de APIs do Chrome**: `fingerprint(numbers)`,
   `countNewSpins(newArr, oldArr)` e `decideRebaseline(streak, maxSkips)`.
2. `countNewSpins` passa a devolver **`{ k, matched, overlap }`**:
   - loop de **`k = 0`** (lista idêntica/re-render = **nenhum** giro novo) até `min(len(new), 12)`;
   - `overlapLen = min(len(old), len(new) - k)`; `overlapLen <= 0` → `break`;
   - **evidência mínima**: rejeitar match com overlap insuficiente em k alto (ex.: `k > 6 &&
     overlap < 2`) — 1 número de prova é **1/37** de coincidência, o mesmo defeito que o SPR-V1
     corrige no servidor;
   - sem alinhamento → `{ k: 0, matched: false, overlap: 0 }`, e o chamador **não envia nada**.
   - Robusto a números repetidos (0-36): é alinhamento **posicional** de subsequência, não conjunto.
3. `fingerprint` cobre os **12** números usados pelo alinhamento (não 5) — mesma janela do
   `allNumbers` enviado. Atualize **as três** escritas de `lastHash` (`:391`, `:1127`, `:1508`).
4. Testes com **`node --test`** (sem framework, sem dependência nova) em `tests/js/`: k=0, k=1, k=n,
   cauda truncada, lista mais curta, repetidos, overlap insuficiente, arrays vazios/inválidos.

### Bloco 2 — single-writer concreto (não um "mutex" vago)
1. **O background é o único escritor do state.** O popup **envia comandos** (mensagens) e nunca grava
   estado concorrente direto.
2. Criar uma fila serial `mutateState(fn)` que serializa **todo** read-modify-write:
   `readResults`, handlers de `state_sync`/`sessao_resetada`, `setDirection`/toggle, re-hidratação e
   qualquer `getState`+`saveState`. Nenhuma chamada longa (`executeScript`, WS, rede) **dentro** da
   seção crítica — computa fora, aplica dentro. Documente o invariante no topo do arquivo.
3. **Guard de reentrância** em `readResults` (`_readBusy`): tick anterior ainda rodando → retorna;
   `finally` sempre libera.
4. **Fim da corrida de boot**: re-hidratação vira **promise de topo** (recriada a cada wake do SW;
   `storage.get` resolve `{}` se vazio — sem deadlock), aguardada por **todos** os consumidores:
   `readResults`, `socket.onmessage` (handlers de `state_sync`/`sessao_resetada`, `:576-611`) e
   `setDirection` (`:1241`).
5. **Seção crítica do flip**: marcada **antes** de computar `sendDir` e liberada **depois** do
   `storage.set` que persiste o flip — senão um `state_sync` chegando no meio regrava a direção velha.

### Bloco 3 — não fabricar giro (furos C/C2)
1. No fluxo de `:1704-1720`: `const { k, matched } = countNewSpins(...)`.
   - `!matched` → **não envia, não flipa, não atualiza baseline**; incrementa
     `state.unalignedStreak` e `state.debug.skippedUnaligned` (**persistidos** — o SW dorme entre
     ticks, um global não sobrevive) com o **motivo** do skip; `saveState`; `return`.
   - `matched && k === 0` → re-render idêntico: `saveState` e `return` (nada novo).
   - `matched && k >= 1` → zera `unalignedStreak` e segue o fluxo atual.
2. **Re-baseline** após `DIR20_MAX_SKIPS` (=5, ≈10s no tick de 2s): aceita a lista como novo baseline
   **sem enviar giro**. `historico_inicial` **somente** com evidência de troca de mesa
   (table/round mudou em `sessionData`); gap na mesma mesa = re-baseline **silencioso** (o servidor
   já tem o histórico e recupera gaps — é o SPR-V1).
3. **Seleção de frame sticky-first** (`:1492-1500`): prioridade (1) o **mesmo** frame da última
   leitura boa (`state.lastGoodFrameId`), se respondeu com números; (2) fallback: a lista mais longa
   entre os demais. *Motivo:* "maior lista vence" pode escolher o **lobby** (lista mais longa de outra
   mesa) e, combinado com o re-baseline, re-ancorar na mesa errada em 10s. `frameId` é estável
   durante a vida do frame; iframe recriado → sticky falha → fallback assume (degrada com graça).
4. **Kill-switch**: constante `DIR20_ENABLED` no topo do `background.js`; `false` + reload restaura o
   comportamento v3.9.1 em ~30s, sem git.

### Bloco 4 — perda observável (senão o fix vira parada silenciosa)
1. Persistir e **transmitir**: `unalignedStreak`, `skippedUnaligned`, `rebaselines`, motivo do skip,
   `frameId`/`round` selecionado e a **versão da extensão** — no payload de `novo_resultado` (campos
   **aditivos**; o servidor antigo ignora) e no popup.
2. **Heartbeat — contrato definido aqui (o servidor só o consome no SPR-V6A).** Durante uma sequência
   não alinhada **nenhum** `novo_resultado` é enviado, logo a telemetria **não pode** viajar só no
   próximo giro. Emita, no keepalive/ping que a extensão **já envia**, um bloco aditivo:
   `client_health: {ext_version, unaligned_streak, skipped_unaligned, rebaselines, last_reason, frame_id, ts_ms}`.
   - **Não crie mensagem nem endpoint novo.** Se o keepalive atual não existir, use o `ping` existente;
     se nem isso existir, registre no Log e **pare para consultar o Diretor** — inventar mensagem muda
     o contrato WS e sai do escopo.
   - Servidor atual **ignora chave desconhecida** ⇒ aditivo e seguro. Nenhuma mudança em `server/` aqui.
3. **Popup**: exibir `skippedUnaligned`, `rebaselines`, `unalignedStreak` atual e a versão
   (`3.10.0`). Sem isso o passo de rollout não tem validação prática.
4. **Reconciliação contínua com o servidor (condicionada por capability)**: reconciliar
   `currentDirection` com o `sentido.next_direction` do `state_sync` **somente se**
   `state_sync.phase_authority.enabled === true` **e** fora da seção crítica de envio.
   - Esse campo é entregue pelo **SPR-V1, Bloco 4.5** (`phase_authority: {enabled, spin_seq, direction,
     seed_parity, seed_n}`) e vale `true` só quando autoridade **e** buffer-sync estão ativos —
     não é "buffer_sync existe". Se o servidor não o expuser (ou `enabled=false`), a reconciliação
     fica **desarmada** (auto-desarme em qualquer rollback do servidor).
   - **Desfazer o flip local do giro rejeitado**: quando `phase_authority.enabled` e o
     `phase_authority.spin_seq` recebido for **igual ao anterior** (ou seja: o servidor **não** contou
     o giro que acabamos de enviar), o cliente **reverte** `currentDirection` para
     `phase_authority.direction` e incrementa `state.debug.flipsReverted`. Sem isto, o gate DIR21 do
     servidor deixa servidor correto e popup espelhado.
   - `locked=true` **não** congela a alternância: o lock protege a **âncora**; o cliente continua
     seguindo `next_direction`. Não trave o toggle por causa do lock.
   - Implemente o consumidor **tolerante à ausência** (desarmado) e registre no Log — este sprint
     **não** altera nada em `server/`.

## Critério de "pronto" (Definition of Done)
- [ ] `node --test` verde para `phase_align.js`: k=0/k=1/k=n, cauda truncada, repetidos, overlap
      insuficiente, entradas inválidas. **Sem dependência nova** no repo.
- [ ] Fingerprint cobre 12 números nas **três** escritas de `lastHash`.
- [ ] Leitura sem alinhamento: **zero** `novo_resultado` enviado, **zero** flip, baseline intacto,
      contador incrementado e persistido.
- [ ] Re-render idêntico (k=0): nada enviado.
- [ ] Reentrância: dois ticks sobrepostos → **um** único envio. **Determinístico**: no harness
      `node --test`, com promises/fakes controlados (não "abrir duas abas e torcer") — o roteiro manual
      é confirmação, não a evidência.
- [ ] Boot do SW: primeiro envio pós-wake usa a fase do `storage`, **nunca** a literal `'horario'`.
      Determinístico no harness (fake de `storage` que resolve depois do 1º tick).
- [ ] Toggle manual durante `state_sync` divergente: seção crítica respeitada (sem regravação da
      direção velha).
- [ ] **Capability**: com `phase_authority` ausente ou `enabled=false`, a reconciliação fica desarmada
      (teste); com `enabled=true` e `spin_seq` **repetido**, o cliente **reverte** o flip local e
      incrementa `flipsReverted` (teste).
- [ ] Popup mostra `skippedUnaligned`, `rebaselines`, `unalignedStreak` e `3.10.0`; payload carrega os
      mesmos campos (aditivos) e o `client_health` viaja no keepalive existente.
- [ ] `manifest.version` = **3.10.0** + nota de "Load unpacked"/reload no Chrome no corpo do PR.
- [ ] `DIR20_ENABLED = false` restaura o comportamento anterior (verificado no roteiro).
- [ ] **Não-interferência do servidor**: `pytest tests/` completo verde (o payload só ganhou campos
      aditivos; nenhum contrato removido/renomeado).
- [ ] **Artefato de rollback reproduzível** (o agente **não** consegue anexar binário a um PR):
      documente no corpo do PR e no ADENDO o **comando exato** que reconstrói o pacote 3.9.1
      (`git archive <sha-de-3.9.1> extension/ -o ext-3.9.1.zip` ou equivalente) **e o `sha256` do
      resultado**. O operador reconstrói o zip em segundos, sem depender de upload.

## Guardrails (inviolável)
- **INV-3**: nada aqui toca indicação, cobertura ou stake. O cliente só rotula o sentido e decide o
  que **não** enviar.
- **Contrato WS aditivo**: `novo_resultado{numero,direcao,allNumbers,timestamp,trace_id}` permanece;
  campos novos são **adicionais**. Servidor antigo tem de continuar funcionando (matriz de
  coexistência: cliente novo × servidor antigo = seguro, pois a reconciliação fica desarmada sem a
  capability).
- **Kill-switch client-side** é o rollback de 1ª camada; policy/constante nunca "auto-liga".
- **Analogia do default-OFF (decisão consciente, registre no ADENDO):** a extensão **não tem
  `docker-compose.yml`**. O equivalente ao "nasce OFF" aqui é que **nada muda em produção até o
  operador instalar/recarregar a 3.10.0 manualmente** — a distribuição é opt-in por natureza.
  `DIR20_ENABLED` nasce `true` **dentro do pacote 3.10.0** (senão o sprint entrega código morto que
  exigiria re-empacotar para ativar) e é o kill-switch instantâneo sem git. Não replique esse padrão
  em nada do lado servidor.
- **Git**: só no worktree/branch `spr/SPR-V2`; **NUNCA** push/checkout/reset/merge em `main`.
  Entregue por **PR**; não faça merge. Aborte se o working tree começar sujo.
- **Produção intocável**: sem SSH/host/deploy. Não instale nada no Chrome do operador.
- **Não** toque em arquivos do servidor (`server/`, `state/`, `app_config/`) — isso é SPR-V1.
- **Não commitar `graphify-out/`**; sem segredo em commit.

## Validação (rode e cole o resultado no Log)
```
node --test tests/js/            # módulo puro (sem framework)
python -m pytest tests/          # suíte COMPLETA do servidor (contrato aditivo não pode quebrar)
```
**Roteiro manual determinístico (numerado, com resultado esperado por passo — cole no PR):**
1. Minimizar a janela por 2min → `skippedUnaligned > 0` no popup e **zero** envio não alinhado no log do SW.
2. Troca de mesa real → re-baseline em ≤5 ticks + `historico_inicial` (com evidência de troca) e
   **nenhum** `novo_resultado` espúrio.
3. Matar o SW em `chrome://serviceworker-internals` durante um giro → 1º envio pós-boot com a fase do
   storage (nunca `'horario'` literal).
4. Toggle manual de direção durante um `state_sync` divergente → sem regravação da direção velha.
5. `DIR20_ENABLED=false` + reload → comportamento v3.9.1.

> **Premissa MV3 documentada no PR:** `periodInMinutes: 0.0333` (2s) só é honrado em extensão
> **unpacked** (o deploy real do operador). Empacotada, o Chrome clampa para 30s → a lógica continua
> correta, mas o re-baseline vira ~150s e `k>1` vira norma.

## Rollback (ISO — 3 camadas)
1. Constante `DIR20_ENABLED = false` + reload (~30s), sem git.
2. `git revert` do PR (~2min pós-merge — mas a extensão do operador só muda ao reinstalar).
3. Zip/tag `ext-v3.9.1` anexado a este PR + "Load unpacked" (3 linhas documentadas, ~3min).

## Ordem de ativação em produção (do Diretor/operador — **não** é DoD deste PR)
Merge deste PR **não** altera produção sozinho (a extensão roda na máquina do operador). Instalar
**depois** do deploy do SPR-V1 com `SDA_PHASE_BUFFER_SYNC=1`, e **antes** de ligar
`SDA_MIN_SPIN_INTERVAL_MS`. Critério de 24h: giros recebidos dentro de **±10%** do baseline —
variação maior bloqueia o avanço (é sinal de perda silenciosa).

## Conformidade ISO (marque ANTES de abrir o PR)
- [ ] Comportamento novo desligável (kill-switch) e **aditivo** no contrato WS.
- [ ] **INV-3** intacto; `pytest tests/` completo verde; `node --test` verde.
- [ ] Mexeu em `extension/` → **bump `manifest.version` (3.10.0)** + nota de reload no Chrome.
- [ ] Nenhum `except`/`catch` silencioso novo: todo descarte é **contado e logado**.
- [ ] Zip da versão anterior anexado ao PR (obrigação de rollback ISO).

## Closeout (a ORDEM importa)
1. **Validação** (automática + roteiro manual) → colar no `## Log`.
2. **ADENDO ISO** em `Manutenabilidade_iso.md` (capacidades, impacto por característica, scorecard
   delta, obrigações, **Rollback de 3 camadas**, premissa unpacked).
3. **Code-review pós-implantação** (subagent `code-review`) → corrigir antes do PR.
4. **Append** no `## Log`.
5. `graphify update .` local → **NÃO commitar `graphify-out/`**.
6. `git status` → commitar tudo (código + ADENDO + este brief com o Log) em `spr/SPR-V2`,
   trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
7. `git push -u origin spr/SPR-V2` e **abrir PR** (NÃO fazer merge), com o roteiro manual e o zip 3.9.1.
8. `store_memory` do achado durável; avisar o Diretor: *"PR de SPR-V2 aberto"*.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
